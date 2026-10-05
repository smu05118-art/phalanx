#!/usr/bin/env python3
"""팔랑크스 생성물을 실행하지 않고 읽어 업체별 관측 원장과 연동 점검을 만든다."""
import argparse
import copy
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlsplit

SCHEMA = 'cloud_signals/1'
LIMIT = 5_000_000
AXES = {'demand', 'delivery', 'contracts', 'pricing', 'funding'}
OFFICIAL = {'assets.nebius.com', 'nebius.com', 'investors.coreweave.com',
            'www.aboutamazon.com', 'ir.aboutamazon.com', 'news.microsoft.com',
            'www.microsoft.com', 'www.sec.gov', 'abc.xyz', 'investor.oracle.com'}
LABELS = {
 'cloud_revenue':'클라우드 매출', 'revenue':'전사 매출', 'revenue_usd_m':'전사 매출',
 'cloud_growth_pct':'클라우드 매출 YoY', 'revenue_yoy_pct':'전사 매출 YoY',
 'segment_revenue':'세그먼트 매출', 'segment_growth_pct':'세그먼트 매출 YoY',
 'cloud_op_income':'클라우드 영업이익', 'op_income':'영업이익',
 'arr_usd_m':'ARR (회사 정의)', 'arr_musd':'ARR (회사 정의)',
 'rpo_usd_m':'RPO (원본 필드·정의 확인 필요)', 'rpo_busd':'RPO',
 'rpo_backlog_busd':'RPO/백로그 (정의 확인 필요)', 'backlog_busd':'백로그',
 'power_mw_active':'가동 전력', 'active_mw':'가동 전력', 'connected_mw':'연결 전력',
 'contracted_mw':'계약 전력', 'power_gw_contracted':'계약 전력', 'gpu_count':'GPU 수', 'gpus':'GPU 수',
 'capex':'CAPEX', 'capex_usd_m':'CAPEX', 'fcf':'FCF', 'ocf':'영업현금흐름',
 'cloud_adj_ebita':'클라우드 조정 EBITA', 'adj_ebitda':'조정 EBITDA',
 'cloud_revenue_yoy_pct':'클라우드 매출 YoY', 'ai_revenue':'AI 매출',
 'public_cloud_revenue':'퍼블릭 클라우드 매출', 'enterprise_cloud_revenue':'기업 클라우드 매출',
 'genai_book_of_business_busd':'생성 AI 누적 수주', 'ms_cloud_revenue':'Microsoft Cloud 매출'}
ALIASES = {'MSFT':['Microsoft','Azure'], 'AMZN':['Amazon','AWS'], 'GOOGL':['Google','Alphabet','GCP'],
 'ORCL':['Oracle','OCI'], 'NBIS':['Nebius'], 'CRWV':['CoreWeave'], 'IREN':['IREN'],
 'APLD':['Applied Digital'], 'CIFR':['Cipher'], 'WULF':['TeraWulf'], 'CRUSOE':['Crusoe'],
 'LAMBDA':['Lambda'], '9988.HK':['Alibaba'], '0700.HK':['Tencent'], '9888.HK':['Baidu']}
ASP_IDS = {'AWS':'AMZN','Azure':'MSFT','GCP':'GOOGL','OCI':'ORCL','Alibaba Cloud':'9988.HK',
           'Tencent Cloud':'0700.HK','Baidu AI Cloud':'9888.HK'}


def stable(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def read_assignment(path, global_name):
    text = Path(path).read_text()
    match = re.match(r'\s*window\.' + re.escape(global_name) + r'\s*=\s*', text)
    if not match:
        raise ValueError(f'{path}: JSON 전역 계약 불일치')
    data, end = json.JSONDecoder().raw_decode(text[match.end():])
    if text[match.end()+end:].strip() not in ('', ';') or not isinstance(data, dict):
        raise ValueError(f'{path}: JSON 외 코드 또는 잘못된 구조')
    return data


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def date(value):
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError):
        raise ValueError('잘못된 일자: ' + str(value)) from None


def public_url(value):
    if not isinstance(value, str):
        return False
    u = urlsplit(value)
    return u.scheme == 'https' and bool(u.hostname) and not u.username and not u.password and u.port in (None, 443)


def metric_axis(metric):
    if any(x in metric for x in ('rpo','backlog','book_of_business')): return 'contracts'
    if any(x in metric for x in ('mw','power','gpu')): return 'delivery'
    if any(x in metric for x in ('fcf','ocf','capex','income','ebit')): return 'funding'
    return 'demand'


def unit(metric, currency='USD'):
    if 'pct' in metric or 'margin' in metric: return '%'
    if 'gw' in metric: return 'GW'
    if 'mw' in metric: return 'MW'
    if 'gpu' in metric: return '대'
    if 'busd' in metric: return 'USD B'
    return currency + ' M'


def import_signals(aid):
    cloud = aid['cloud']
    providers, signals = {}, []
    def add(co, metric, period, value, src, origin, scope, kind='unverified', note=''):
        if not number(value) or not re.fullmatch(r'\d{4}-Q[1-4]', period): return
        if metric not in LABELS: return
        signals.append(dict(key=f'{origin}:{co}:{metric}:{period}', provider=co,
            axis=metric_axis(metric), metric=metric, period=period, value=value,
            unit=unit(metric,providers[co]['currency']), evidence=kind, verified=False,
            published_at=None, effective_at=None, direction=None, source_url=src if public_url(src) else None,
            source_path=origin, title=LABELS[metric], scope=scope, note=note,
            origin='legacy', correlation_group=f'{co}:{metric_axis(metric)}:{period}'))
    for region in ('west','china'):
        companies = cloud.get(region,{}).get('companies')
        if not isinstance(companies,dict) or not companies:
            raise ValueError('업체 목록 없음: ' + region)
        for co,c in companies.items():
            if c.get('category') == 'self_infra': continue
            providers[co] = dict(id=co, name=c['name'], group=('china' if region=='china' else
                ('colo' if co in ('APLD','CIFR','WULF') else c.get('category','neocloud'))),
                currency=c.get('ccy','USD'), aliases=ALIASES.get(co,[c['name']]),
                sources=[s for s in c.get('src',[]) if public_url(s)],
                pending=c.get('pending',[]), fiscal_note=c.get('fy_note',''),
                definition=c.get('disclosure_note',''))
            for metric,series in c.get('metrics',{}).items():
                if not isinstance(series,dict): continue
                for period,value in sorted(series.items())[-8:]:
                    src=next(iter(providers[co]['sources']), None)
                    add(co,metric,period,value,src,'AID.cloud',c.get('metric_defs',{}).get(metric,LABELS.get(metric,metric)),
                        note='기존 클라우드 데이터는 오프라인·원자료 미대조. 원본 conf 등급과 무관하게 점수에서 제외.')
    for co,c in aid.get('neocloud',{}).get('companies',{}).items():
        if co not in providers: continue
        for period,row in c.get('quarterly',{}).items():
            for metric,value in row.items():
                note='기존 모델의 수치. 공시 URL 존재만으로 검증 완료로 보지 않음.'
                if co=='NBIS' and metric=='rpo_usd_m': note='기존 모델 주석은 선수수익이라고 명시. RPO로 합산 금지.'
                if co=='NBIS' and metric=='contracted_mw': note='연말 계약전력 목표와 분기말 실적의 혼재 가능성. 가동 MW로 사용 금지.'
                if co=='CRWV' and metric=='rpo_usd_m': note='공식 발표 정의는 revenue backlog (RPO와 기타 약정 포함). 순수 RPO와 구분.'
                if co=='IREN' and metric=='revenue_usd_m': note='비트코인 채굴 포함 전사 매출. AI 클라우드 단독 매출 아님.'
                add(co,metric,period,value,row.get('src'),'AID.neocloud',LABELS.get(metric,metric),
                    'target' if row.get('guidance') else 'unverified', note)
    for co,c in aid.get('capex',{}).get('companies',{}).items():
        if co not in providers: continue
        for metric in ('capex','fcf','ocf'):
            for period,value in sorted(c.get(metric,{}).items())[-8:]:
                add(co,metric,period,value,next((s for s in c.get('src',[]) if public_url(s)),None),
                    'AID.capex','전사 기준 · '+c.get(metric+'_def',metric),
                    note='SEC/IR 기반 기존 파이프라인. 이번 원장의 개별 원자료 검증 전까지 점수 제외.')
    return providers, signals


def validate_observation(s, providers, today):
    if s.get('provider') not in providers or s.get('axis') not in AXES: raise ValueError('잘못된 업체/축')
    for k in ('key','title','metric','period','unit','scope','note','correlation_group'):
        if not isinstance(s.get(k),str) or not s[k]: raise ValueError('필수 문자열 없음: '+k)
    if not number(s.get('value')): raise ValueError('관측값 누락')
    if s.get('direction') is not None and (type(s['direction']) is not int or s['direction'] not in (-1,0,1)): raise ValueError('방향 범위 오류')
    if s.get('evidence') not in ('confirmed','target','external','inference','unverified'): raise ValueError('근거 유형 오류')
    if s.get('verified'):
        if not public_url(s.get('source_url')) or urlsplit(s['source_url']).hostname not in OFFICIAL:
            raise ValueError('검증 출처 allowlist 위반')
        if date(s.get('verified_at')) > today or date(s.get('published_at')) > today: raise ValueError('미래 검증/공표일')
        if s.get('direction') is not None and not s.get('rule'): raise ValueError('방향 판정 근거 없음')
    if s.get('effective_at'): date(s['effective_at'])
    if s.get('evidence') != 'confirmed' and s.get('direction') is not None: raise ValueError('실적 외 점수 부여 금지')


def merge_history(old, incoming, today):
    rows = copy.deepcopy(old)
    latest = {r['key']:r for r in rows}
    seen=set()
    for raw in incoming:
        if raw['key'] in seen: raise ValueError('중복 관측 key')
        seen.add(raw['key'])
        digest=hashlib.sha256(stable(raw).encode()).hexdigest()
        prev=latest.get(raw['key'])
        if prev and prev['fingerprint']==digest: continue
        r=dict(raw, fingerprint=digest, revision=(prev['revision']+1 if prev else 1),
               first_seen_at=prev['first_seen_at'] if prev else today, observed_at=today)
        r['id']=hashlib.sha256((raw['key']+':'+str(r['revision'])).encode()).hexdigest()[:20]
        if prev:r['supersedes']=prev['id']
        rows.append(r); latest[raw['key']]=r
    return rows


def integration_audit(root, aid, providers):
    dc=read_assignment(root/'data_dc.js','DCD')
    mem=read_assignment(root/'data_mem.js','MEMD')
    rack=read_assignment(root/'data_rack.js','RACKD')
    tech=read_assignment(root/'data_tech.js','TECHD')
    ins=read_assignment(root/'data_insight.js','INSD')
    rows=aid.get('capex_common',{}).get('rows',[])
    equal=bool(rows) and all(rows==d.get('capex_common',{}).get('rows') for d in (dc,mem,rack))
    projects={}
    for co,p in providers.items():
        aliases={n.casefold() for n in p['aliases']}
        matches=[dict(id=x['id'],name=x.get('n'),operator=x.get('op'),current_mw=x.get('cur'),
                      planned_mw=x.get('plan'),last_date=x.get('ld'), relation='operator' if x.get('op','').casefold() in aliases else 'customer')
                 for x in dc.get('projects',[]) if x.get('op','').casefold() in aliases or any(str(u).casefold() in aliases for u in x.get('us',[]))]
        projects[co]=matches
    checks=[
      dict(id='capex',title='CAPEX 공통 원본',status='ready' if equal else 'conflict',tab='ai',
           count=len(rows),key='기업 ID + 캘린더 분기 + 지표 + 통화·단위',
           detail='AI·메모리·랙·DC의 공통 테이블이 일치함. 네 탭을 네 개 신호로 중복 집계하지 않음.' if equal else '공통 테이블이 서로 다름. 중복 합산 및 점수 반영 보류.'),
      dict(id='dc',title='데이터센터 프로젝트',status='conditional',tab='dc',count=len(dc.get('projects',[])),
           key='운영사/고객 별칭 → 업체 ID + 프로젝트 ID',detail='운영사와 고객 관계를 분리해 연결. 현재/계획 MW, 추정치, 미래 일정이 섞일 수 있어 공시 검증 없이 가동 전력에 합산하지 않음.'),
      dict(id='rack',title='서버·랙 / 대만 ODM',status='conditional',tab='rack',count=len(rack.get('ship',{})),
           key='분기 + 공급망 노출 + 0~2분기 시차',detail='AI 서버 매출·월매출은 수요 교차확인에 사용 가능. 기존 업체별 출하량은 추정치이며 고객 배분 비중은 없어 특정 클라우드 매출로 직접 환산 불가.'),
      dict(id='mem',title='메모리 / HBM',status='conditional',tab='mem',count=len(mem.get('hbm',{}).get('peers',[])),
           key='GPU 세대 + HBM 용량 + 공급사 + 월/분기',detail='HBM 공급·메모리 가격으로 병목 확인 가능. DDR5 현물가를 HBM 계약단가로 대체하지 않음. GPU 세대별 BOM·클라우드 구매 배분 필요.'),
      dict(id='tech',title='테크 공급망',status='conditional',tab='tech',count=len(tech.get('nodes',[])),
           key='기업 ID/티커 + 공급망 단계',detail='칩·패키징·서버·네트워크·전력·DC 운영의 방향을 비교 가능. 공통 CAPEX에서 파생된 항목은 독립 근거가 아님.'),
      dict(id='ins',title='인사이트 / 상충 신호',status='ready',tab='ins',count=len(ins.get('insights',{}).get('signals',{})),
           key='업체 ID + 관측 ID + 근거 그룹 + 공표일',detail='이번 원장과 앙상블 JSON을 읽어 확장 가능. 기존 인사이트 생성기 수신 연결은 운영 빌더에 별도 반영 필요.'),
      dict(id='customs',title='관세·기업수출 / 나우캐스트',status='research',tab='nowcast',count=0,
           key='HS + 국가 + 월 → 품목 → 업체 노출 비중',detail='공급망 모멘텀 비교는 가능하나 클라우드별 고객 매핑이 없음. 최소 20분기 학습·6분기 홀드아웃, 공표일 기준 검증 후 편입.')]
    return dict(checks=checks,projects=projects,shared_capex_equal=equal,
        caveats=['Nebius 선수수익 ≠ RPO; 연말 계약전력 목표 ≠ 가동 전력.',
                 'CoreWeave revenue backlog는 RPO와 기타 약정의 합계. 순수 RPO와 분리.',
                 'Azure는 성장률 중심, Google Cloud는 Workspace 포함. 금액·점유율 단순 합산 금지.',
                 'IREN은 채굴 포함 전사 매출, APLD·CIFR·WULF는 임대/호스팅 노출. GPU 클라우드와 경제성 비교 분리.',
                 'USD/GPU-hour 공개가격, 계약 ACV/MW-year, 장기 임대 총액/MW는 다른 단위.',
                 '공표일 이전 정보로 소급 점수를 만들지 않음. 수집 시작 전 최초 발견 시점은 알 수 없음.'])


def atomic_write(path, payload):
    blob=(stable(payload)+'\n').encode()
    if len(blob)>LIMIT: raise ValueError('5MB 원장 상한 초과')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd,temp=tempfile.mkstemp(dir=path.parent,prefix='.signals-')
    try:
        with os.fdopen(fd,'wb') as f:f.write(blob)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def build(root, today):
    aid=read_assignment(root/'data_ai.js','AID')
    providers,signals=import_signals(aid)
    curated=json.loads((root/'data/cloud_signals/reviewed.json').read_text())
    if curated.get('schema')!=SCHEMA or not isinstance(curated.get('signals'),list):raise ValueError('검증 원장 계약 오류')
    for s in curated['signals']:validate_observation(s,providers,date(today))
    signals+=curated['signals']
    out=root/'data/cloud_signals/ledger.json'
    old=json.loads(out.read_text()) if out.exists() else {'signals':[]}
    if old.get('schema',SCHEMA)!=SCHEMA:raise ValueError('기존 스키마 불일치')
    history=merge_history(old['signals'],signals,today)
    result=dict(schema=SCHEMA,updated=today,tracking_started=old.get('tracking_started',today),
                providers=providers,signals=history,integration=integration_audit(root,aid,providers))
    atomic_write(out,result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[2]);p.add_argument('--today',default=dt.date.today().isoformat());a=p.parse_args()
    date(a.today)
    r=build(a.root,a.today);print(f"업체 {len(r['providers'])}개 · 관측 이력 {len(r['signals'])}개")
