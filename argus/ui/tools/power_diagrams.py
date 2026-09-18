"""Illustrated electricity and generation topology. Company links retain original evidence."""
import html
import json
import re
from pathlib import Path
from urllib.parse import urlparse

SOURCES = {
 'eia': {'label':'EIA · 전기의 이동','url':'https://www.eia.gov/energyexplained/electricity/delivery-to-consumers.php'},
 'kepco': {'label':'한국전력 · 송배전','url':'https://www.kepco.co.kr/home/business/transbus.do'},
 'ls': {'label':'LS ELECTRIC · 계통 구성 p.13','url':'https://www.ls-electric.com/ko/company/data/2025_4%EB%B6%84%EA%B8%B0_%EC%8B%A4%EC%A0%81%EC%9E%90%EB%A3%8C.pdf#page=13'},
 'kpx': {'label':'전력거래소 · 전력계통','url':'https://www.kpx.or.kr/boardDownload.es?bid=0045&list_no=51292&seq=16036'},
 'doe': {'label':'미 에너지부 · 배전변압기','url':'https://www.energy.gov/articles/doe-finalizes-energy-efficiency-standards-distribution-transformers-protect-domestic'},
 'nrc': {'label':'NRC · 가압경수로 원리','url':'https://www.nrc.gov/reading-rm/basic-ref/students/animated-pwr'},
 'ge': {'label':'GE Vernova · 복합발전','url':'https://www.gevernova.com/gas-power/resources/education/combined-cycle-power-plants'},
}

def child(id,label,keys=(),terms=None,note=None):
    d={'id':id,'label':label,'keys':list(keys)}
    if terms:d['terms']=terms
    if note:d['note']=note
    return d

def node(id,label,icon,x,y,unit,note,children,refs,tag=None,color=None,link=None):
    d=dict(id=id,label=label,icon=icon,x=x,y=y,unit=unit,note=note,children=children,refs=refs)
    if tag:d['tag']=tag
    if color:d['color']=color
    if link:d['link']=link
    return d

def edge(d,kind='electric',label=None,lx=None,ly=None,**kw):
    return dict(d=d,kind=kind,**({'label':label,'lx':lx,'ly':ly} if label else {}),**kw)

def grid_scenes():
    # Voltages are Korean examples, not universal ratings or company product certifications.
    common=['kepco','ls']; nodes=[
      node('GEN','발전','plant',100,158,'전기 생산','원전·화력·수력·풍력·태양광 등에서 전기를 만듭니다. 발전원에 따라 계통 연결 방식과 전압이 다릅니다.',[],['eia'],link={'label':'발전소 내부 흐름 보기','url':'../knuke/parts.html'}),
      node('STEPUP','승압 변압기','transformer',290,158,'발전 전압 → 송전 전압','발전소에서 나온 전기의 전압을 높입니다. 같은 전력을 보낼 때 전류를 낮춰 송전 손실을 줄이기 위한 단계입니다.',[child('step-transformer','초고압 변압기',['ehv']),child('step-breaker','차단기·개폐장치',['breaker']),child('step-parts','부싱·절연·부자재',['fitting'],r'부싱|절연|탭체인저|권선|철심')],['eia','ls']),
      node('TRANS','송전','tower',480,158,'154 · 345 · 765 kV 예시','큰 전력을 먼 지역까지 옮깁니다. 가공 송전선과 철탑뿐 아니라 지중·해저 케이블도 사용합니다. 아래 HVDC는 별도 변환소를 사용하는 송전 방식입니다.',[child('trans-cable','전력선·케이블',['cable']),child('trans-tower','철탑·금구·애자',['fitting'],r'철탑|금구|애자|가공선')],common),
      node('SUB','강압 변전소','substation',670,158,'345 → 154 → 22.9 kV 예시','수요지에 가까워지며 전압을 단계적으로 낮춥니다. 모든 선로가 이 전압 단계를 전부 거치는 것은 아닙니다. 변압기는 전압을 바꾸고, 차단기·보호계전기는 고장을 감지·분리합니다.',[child('sub-transformer','전력용 변압기',['ehv']),child('sub-breaker','차단기·개폐장치',['breaker','switch']),child('sub-relay','보호계전·감시제어',['relay'])],common),
      node('DIST','배전선로','pole',860,158,'22.9 kV 예시','변전소에서 동네·건물 주변으로 전기를 나눠 보냅니다. 전주 위 가공선 또는 지중 케이블, 개폐기·리클로저와 배전자동화 설비가 놓입니다.',[child('dist-switch','개폐기·리클로저',['switch']),child('dist-cable','배전 전선·케이블',['cable']),child('dist-relay','배전자동화·보호제어',['relay'])],common),
      node('POLE','주상·지상 변압기','poletr',1050,158,'22.9 kV → 저압 예시','주상형은 전주에, 지상형은 지면의 외함 안에 설치합니다. 고객 가까이에서 전압을 낮추는 같은 배전 단계의 대안입니다. 두 형식을 직렬로 모두 거치는 뜻은 아닙니다.',[child('pole-transformer','주상변압기',['dist_tr'],r'주상',note='주상이라는 형식이 제품 근거 또는 공식 제품 자료에 직접 나온 기업만 연결합니다.'),child('pad-transformer','지상·패드 변압기',['dist_tr'],r'지상|패드|pad.?mount',note='지상·패드 형식이 제품 근거에 직접 나온 기업만 연결합니다.'),child('distribution-transformer','배전용 변압기 전체',['dist_tr'],note='배전용으로 분류된 전체 목록입니다. 주상·지상·몰드·건식은 서로 다른 형식이므로 이 목록을 특정 형식의 제조사 목록으로 읽지 않습니다.')],['doe','kpx']),
      node('HOME','주택·소규모 상가','home',1240,158,'220 / 380 V 예시','배전변압기를 거친 저압 전기를 사용합니다. 건물 안에서는 계량·분전·차단 설비를 거쳐 조명과 기기에 전달됩니다.',[child('home-panel','수배전·분전 설비',['switchgear']),child('home-meter','계량·보호기기',['relay'])],['kpx','ls']),
      node('HVDC','HVDC 직류송전','converter',480,438,'양단 변환소 + 직류선로','교류를 직류로 바꾸어 보내고 반대편에서 다시 교류로 변환합니다. 일반 교류 송전과 구별한 선택 경로입니다. 인버터나 PCS를 만든다는 이유만으로 HVDC 밸브 제조사로 분류하지 않습니다.',[child('hvdc-equipment','HVDC 명시 제품',['ehv','hvdc','cable','fitting'],r'HVDC|초고압직류|직류송전',note='제품 근거에 HVDC·직류송전이 직접 명시된 경우만 연결합니다. 전력변환기 일반 분류를 대신 넣지 않습니다.')],common,tag='송전의 다른 경로',color='#b2a0da'),
      node('LOAD','공장·데이터센터','factory',770,438,'고압·특고압 수전','큰 수요처는 송전망 또는 배전망에서 전기를 받아 자체 변압기·수배전반으로 낮춰 씁니다. 주상변압기 경로를 반드시 거치지 않습니다. 수전 전압과 UPS·ESS 구성은 현장마다 다릅니다.',[child('load-panel','수배전반',['switchgear']),child('load-transformer','구내 배전용 변압기',['dist_tr']),child('load-ups','UPS·전력변환',['converter']),child('load-relay','보호·계측',['relay'])],['kpx','ls'],tag='별도 수전 경로',color='#8ab5d1'),
      node('DER','태양광·ESS','solar',1070,438,'분산전원 · 저장','태양광은 계통으로 전력을 공급하고 ESS는 충전·방전합니다. 계통 연결용 인버터·PCS와 보호·개폐 설비를 거칩니다. 전력 흐름이 발전소에서 고객으로만 향하는 것은 아닙니다.',[child('der-converter','인버터·ESS PCS',['converter']),child('der-protect','연계 보호·개폐',['switch','relay'])],['ls','kepco'],tag='지역 계통 연계',color='#83c7b4'),
    ]
    edges=[edge(f'M{x+63} 158H{y-64}') for x,y in zip([100,290,480,670,860,1050],[290,480,670,860,1050,1240])]
    edges += [edge('M382 158V438H416','electric',branch=True),edge('M544 438H574V158H606','electric',branch=True),edge('M670 276V325H770V342','electric','고압 직접 수전',738,314,branch=True),edge('M860 276V340H823V385','electric','배전망 수전',922,331,branch=True),edge('M1134 438H1180V315H860V276','control','계통 연계',1020,304,branch=True,both=True)]
    return [dict(id='GRID',title='발전에서 소비까지, 전기가 움직이는 길',width=1340,height=580,nodes=nodes,edges=edges,labels=[dict(x=24,y=35,text='01 — 광역 전력망에서 지역 배전망으로'),dict(x=24,y=350,text='02 — 별도 수전 · 계통 연계')],legend=[dict(kind='electric',label='주요 전력 전달 방향'),dict(kind='control',label='연계·충방전')],caveat='한국 전압의 대표 예시 · 실제 망은 다중 경로')]


def plant_scenes(tax):
    names={c['id']:c['ko'] for c in tax['cats']}
    def children(*ids):return [child(i,names[i]) for i in ids]
    refs=['nrc']; rows=[
      node('REACTOR','원자로','reactor',110,190,'핵분열 → 열','가압경수로(PWR)의 원자로가 열을 만듭니다. 1차 냉각재는 압력 아래에서 끓지 않고 열을 증기발생기로 옮깁니다. 격납건물은 이 계통을 둘러싼 방호 구조입니다.',children('NSSS.RV','MAT.FORGE'),refs),
      node('SG','증기발생기','steamgen',355,190,'1차 열 → 2차 증기','1차 냉각재의 열을 별도 2차 물에 전달해 증기를 만듭니다. 두 계통의 물은 서로 섞이지 않습니다.',children('NSSS.SG'),refs),
      node('TURB','증기터빈','turbine',650,190,'증기 → 회전력','2차 계통의 증기가 터빈 날개를 돌립니다. 증기는 발전기 안으로 흐르지 않으며, 회전축으로 발전기에 힘을 전달합니다.',children('TG.TURBINE','MAT.FORGE'),refs),
      node('GEN','발전기','generator',890,190,'회전력 → 전기','터빈과 연결된 회전축의 기계적 에너지를 전기로 바꿉니다. 그 뒤 변압기가 송전용 전압으로 높입니다.',children('TG.GEN'),refs),
      node('TRANSF','승압·계통 연결','transformer',1180,190,'발전소 → 전력망','발전기 전기를 승압하고 차단·개폐 설비를 거쳐 계통으로 보냅니다. 세부 송배전 흐름은 전력기기 인포그래픽에서 이어집니다.',children('ELEC.SWGR','ELEC.CABLE'),['ls'],link={'label':'송전·배전 밸류체인 보기','url':'../kgrid/grid.html'}),
      node('PZR','가압·냉각재 순환','pump',110,485,'1차 계통 보조','가압기는 1차 계통 압력을 조절하고 냉각재펌프는 물을 순환시킵니다. 원자로에서 나온 열을 안정적으로 증기발생기로 전달합니다.',children('NSSS.SG','BOP.PUMP'),refs,tag='1차 계통'),
      node('FUEL','핵연료·취급 설비','fuel',355,485,'연료 장전 · 교체','핵연료 집합체와 연료를 취급·이송하는 설비입니다. 정상 발전 중의 증기·전력 흐름과 구분합니다.',children('NSSS.FUEL'),refs,tag='연료 계통'),
      node('COND','복수기·급수','condenser',650,485,'증기 → 물 → 재사용','터빈에서 나온 증기를 냉각해 물로 되돌리고 다시 증기발생기로 보냅니다. 바다·강·냉각탑 등의 냉각수 계통은 발전소 설계에 따라 다릅니다.',children('BOP.HX','BOP.VESSEL','BOP.PUMP'),refs,tag='2차 계통'),
      node('IC','계측·보호제어','control',1000,485,'상태 측정 · 제어','센서와 계측제어 시스템이 발전소 상태를 감시·제어합니다. 계측 신호를 표시한 점선은 전력 또는 증기 배관이 아닙니다.',children('IANDC.MMIS','IANDC.INSTR'),refs,tag='감시·제어',color='#83c7b4'),
    ]
    npp=dict(id='NPP',title='원전 — 가압경수로(PWR)',width=1340,height=650,nodes=rows,
      boundaries=[dict(x=15,y=35,w=435,h=300,label='격납계통 · 1차 냉각재')],
      edges=[edge('M168 167H297','heat','1차 냉각재',232,154),edge('M299 223H166','water','1차 순환',232,248),edge('M410 169H585','steam','2차 증기',503,155),edge('M712 191H825','shaft','회전축',766,178),edge('M952 191H1115','electric','전기',1038,178),edge('M650 308V388','steam'),edge('M587 485H492V228H417','water','2차 급수',485,367),edge('M1000 388V330H890V308','control',branch=True)],
      legend=[dict(kind='heat',label='1차 냉각재의 열'),dict(kind='steam',label='2차 증기'),dict(kind='water',label='물·냉각재 순환'),dict(kind='shaft',label='회전축'),dict(kind='electric',label='전기')],caveat='PWR 원리도 · 1차/2차 물은 섞이지 않음')
    fossil=[
      node('GT','가스터빈','turbine',130,175,'연료 연소 → 회전력','천연가스를 공기와 연소시켜 터빈을 돌립니다. 회전축은 발전기를 구동하고, 뜨거운 배기가스는 배열회수보일러로 이동합니다.',children('TG.TURBINE'),['ge']),
      node('GEN2','가스측 발전기','generator',130,465,'회전력 → 전기','가스터빈에서 전달한 회전력으로 전기를 만듭니다. 이 그림은 가스터빈·증기터빈에 별도 발전기를 둔 다축 구성 예시입니다.',children('TG.GEN'),['ge'],tag='1차 발전'),
      node('BOILER','배열회수보일러','boiler',425,175,'배기가스의 열 → 증기','가스터빈 배기가스의 열을 회수해 증기를 만듭니다. 석탄화력 보일러와 같은 장치로 합쳐 그리지 않습니다. HRSG는 배기가스와 물·증기를 분리해 열을 전달합니다.',children('BOP.BOILER'),['ge']),
      node('STURB','증기터빈','turbine',715,175,'회수한 증기 → 회전력','배열회수보일러가 만든 증기가 터빈을 돌려 추가 전력을 생산합니다. 발전 후 증기는 복수기로 보내 물로 되돌립니다.',children('TG.TURBINE'),['ge']),
      node('CCGEN','증기측 발전기','generator',940,175,'회전력 → 전기','증기터빈의 회전력으로 전기를 추가 생산합니다. 실제 발전소에는 두 터빈을 하나의 발전기에 연결한 단축 구성도 있습니다.',children('TG.GEN'),['ge']),
      node('CCTR','승압·계통 연결','transformer',1210,175,'두 발전계통 → 전력망','가스측·증기측 발전 전기를 계통으로 전달합니다. 발전소마다 변압기와 전기 모선 구성은 다릅니다.',children('ELEC.SWGR','ELEC.CABLE'),['ls']),
      node('STACK','배출가스 처리','stack',425,465,'탈질 · 연돌','HRSG를 지난 배기가스는 배출 설비로 향합니다. LNG 복합에서는 탈질 등이 사용되며, 탈황·집진은 연료와 설비 구성에 따라 달라집니다. 회사 분류는 기존 환경설비 제품군입니다.',children('BOP.ENV'),['ge'],tag='배기가스 경로'),
      node('CCCOND','복수기·급수','condenser',715,465,'증기 → 물 → HRSG','증기를 냉각해 물로 만들고 급수펌프로 배열회수보일러에 돌려보냅니다.',children('BOP.HX','BOP.PUMP','BOP.VESSEL'),['ge'],tag='물·증기 순환'),
      node('CCIC','계측·보호제어','control',1030,465,'감시 · 보호 · 제어','가스·증기·전기 계통의 운전 상태를 감시하고 제어합니다. 안전과 보호 기능의 구체적 구성은 발전소마다 다릅니다.',children('IANDC.MMIS','IANDC.INSTR'),['ge'],tag='감시·제어',color='#83c7b4'),
    ]
    fossil.sort(key=lambda n: ['GT','BOILER','STURB','CCGEN','CCTR','GEN2','STACK','CCCOND','CCIC'].index(n['id']))
    cc=dict(id='FOSSIL',title='LNG 복합발전',width=1340,height=625,nodes=fossil,
      edges=[edge('M192 175H361','heat','고온 배기가스',280,160),edge('M489 175H650','steam','회수 증기',570,160),edge('M777 175H877','shaft','회전축',827,161),edge('M1003 175H1147','electric'),edge('M130 297V366','shaft'),edge('M195 465H280V610H1295V175H1272','electric','가스측 전기',260,595),edge('M425 297V366','heat'),edge('M715 297V366','steam'),edge('M652 465H574V213H489','water','급수',567,348)],
      legend=[dict(kind='heat',label='배기가스·열'),dict(kind='steam',label='증기'),dict(kind='water',label='물'),dict(kind='shaft',label='회전축'),dict(kind='electric',label='전기')],caveat='다축 LNG 복합 예시 · 실제 발전소 배치와 다름')
    return [npp,cc]


def markup(payload,title,intro,stats):
    e=html.escape
    tabs=''.join('<button type="button" data-scene="%s" aria-pressed="false">%s</button>'%(e(s['id']),e(s['title'])) for s in payload['scenes'])
    stats=''.join('<div><b>%s</b><span>%s</span></div>'%(e(str(v)),e(k)) for k,v in stats)
    js=json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    return '''<link rel="stylesheet" href="../ui/power-atlas.css?v=1">
<div class="pa-hero"><div><div class="pa-kicker">ARGUS / POWER SYSTEMS</div><h2>'''+e(title)+'''</h2><p>'''+e(intro)+'''</p></div><div class="pa-stats">'''+stats+'''</div></div>
<section id="power-atlas"><div class="pa-surface"><div class="pa-toolbar"><div class="pa-tabs">'''+tabs+'''</div><div class="pa-actions"><button type="button" data-motion aria-pressed="false">흐름 재생</button><button type="button" data-reset>처음으로</button></div></div><div class="pa-mobile-hint">그림을 좌우로 밀거나 아래 설비 이름을 눌러 탐색하세요.</div><div class="pa-diagram-wrap"></div><div class="pa-legend"></div><div class="pa-stepnav" aria-label="설비 바로 선택"></div></div><div class="pa-detail" id="pa-detail"><div class="pa-context"></div><div class="pa-companies"></div></div><span class="pa-sr" role="status"></span></section>
<details class="pa-research"><summary>도식의 기준과 자료 출처</summary><ul>'''+''.join('<li>'+e(t)+'</li>' for t in payload['notes'])+'''</ul>'''+''.join('<a href="'+e(s['url'])+'" target="_blank" rel="noopener noreferrer">'+e(s['label'])+' ↗</a>' for s in payload['sources'].values())+'''</details>
<script src="../ui/power-atlas.js?v=1"></script><script>PowerAtlas.start('''+js+''');</script>'''


def plant_payload(tax,idx,pages):
    rows={}
    for k,cos in idx.items():
        rows[k]=[dict(stock=c['stock'],nm=c['nm'],proofs=[{'src':{'contract':'계약명','body':'정기보고서 본문','kind':'KIND 주요제품'}.get(c['src'],c['src']),'text':c['kw']+' · '+c['prod']}],primes=c.get('primes',[])) for c in cos]
    scenes=plant_scenes(tax)
    # Every existing taxonomy, including design/O&M, remains directly selectable.
    extra=[c for c in tax['cats'] if not any(c['id']==p['id'] for s in scenes for n in s['nodes'] for p in n['children'])]
    # Keep common services as one selectable scene rather than overlapping physical equipment.
    service_nodes=[node('SERVICE-'+c['id'].replace('.','-'),c['ko'],'control',180+i*320,175,'설계 · 운영 지원','발전소 전 생애주기의 '+c['ko']+' 분야입니다. 기업 연결은 기존 계약·보고서 분류 근거를 사용합니다.',[child(c['id'],c['ko'])],[],tag='공통 서비스') for i,c in enumerate(extra)]
    if service_nodes:scenes.append(dict(id='SERVICE',title='설계·정비·검사',width=1340,height=320,nodes=service_nodes,edges=[],legend=[],caveat='물리적 설비의 직렬 흐름과 구분'))
    return dict(scenes=scenes,rows=rows,pages=pages,sources={k:SOURCES[k] for k in ['nrc','ge','ls']},default_node='SG',aliases={'CONTAIN':'REACTOR','PUMP':'CCCOND'},company_note='그림의 장비 → 세부 품목 → 기업 순서로 탐색합니다. 분류는 기존 계약명·정기보고서·KIND 문구 기준이며 특정 발전소의 납품을 뜻하지 않습니다.',notes=['원전은 가압경수로(PWR), 복합발전은 LNG 다축 구성을 설명하는 개념도입니다. 설비 축척·실제 배치는 표현하지 않습니다.','원전의 1차 냉각재와 2차 물·증기는 섞이지 않습니다. 터빈과 발전기의 연결은 증기 배관이 아니라 회전축입니다.','기존 부품 분류·기업 근거를 유지했습니다. 일반적인 장비 역할 설명과 기업의 실제 납품 근거는 별개입니다.'])


def grid_payload(summaries,pages):
    scenes=grid_scenes();rows={};all_by_key={}
    for s in summaries:
        if s['role']=='holding':continue
        for k in s['products']:
            proofs=[dict(src=w['src'],text=w['text']) for w in s['product_why'] if w['key']==k]
            if k == 'dist_tr':
                proofs = [p for p in proofs if re.search(r'변압|transformer', p['text'], re.I) and not re.search(r'주상복합', p['text'])]
            if not proofs:continue
            r=dict(stock=s['stock'],nm=s['name'],proofs=proofs)
            if s['backlog'] is not None:
                r['metric']=('수주잔고 '+format(round(s['backlog']/100),',')+'억' if s['cur']=='KRW' else s['cur']+' 공시 · 환산 안 함')+' · '+str(s.get('quarter') or '')
            all_by_key.setdefault(k,[]).append(r)
    catalog=json.loads(Path(__file__).with_name('power_product_evidence.json').read_text())
    by_stock={s['stock']:s for s in summaries if s['role']!='holding'}
    allowed={'www.cheryongelec.com','www.hyosungheavyindustries.com','www.ls-electric.com','www.hyundai-electric.com'}
    for item in catalog['rows']:
        u=urlparse(item['url'])
        if u.scheme!='https' or u.hostname not in allowed:
            raise ValueError('Untrusted official product source')
        s=by_stock.get(item['stock'])
        if not s:continue
        r=dict(stock=s['stock'],nm=s['name'],proofs=[dict(src='공식 제품 자료 · '+catalog['checked'],text=item['text'],url=item['url'])])
        if s['backlog'] is not None:
            r['metric']=('수주잔고 '+format(round(s['backlog']/100),',')+'억' if s['cur']=='KRW' else s['cur']+' 공시 · 환산 안 함')+' · '+str(s.get('quarter') or '')
        all_by_key.setdefault(item['key'],[]).append(r)
    for n in scenes[0]['nodes']:
        for c in n['children']:
            items=[r for k in c['keys'] for r in all_by_key.get(k,[])]
            if c.get('terms'):
                items=[r for r in items if any(re.search(c['terms'],p['text'],re.I) for p in r['proofs'])]
            rows[c['id']]=items
    # Preserve uncertain transformer companies in an explicitly uncertain equipment bucket.
    n=scenes[0]['nodes'][1];c=child('unknown-transformer','변압기 · 전압 계급 미확인',['tr_unknown'],note='변압기 제품만 확인됐습니다. 그림의 승압·초고압 기종을 실제로 제조한다는 뜻이 아닙니다.')
    n['children'].append(c);rows[c['id']]=all_by_key.get('tr_unknown',[])
    return dict(scenes=scenes,rows=rows,pages=pages,sources={k:SOURCES[k] for k in ['eia','kepco','ls','kpx','doe']},default_node='POLE',aliases={'DIST_TR':'POLE'},company_note='장비를 누른 뒤 세부 품목을 선택하면 기업을 좁혀 볼 수 있습니다. KIND·수주 품목·제품 매출과 공식 제품 자료를 사용하며 특정 전압·현장 납품을 보증하지 않습니다.',notes=['전압은 한국 계통의 대표 예시입니다. 모든 선로가 765 → 345 → 154 kV 순서를 거치지는 않습니다. 실제 전력망은 여러 경로로 연결됩니다.','송전탑·가공선, 지중·해저 케이블은 송전 방식의 선택지입니다. HVDC는 양단 변환소가 필요한 별도 송전 경로입니다.','주상형과 지상형 변압기는 같은 배전 단계의 설치 형태입니다. 주상 → 지상을 차례로 통과하는 흐름이 아닙니다.','주상·지상·HVDC 세부 기업은 제품 근거 또는 공식 제품 자료에 해당 기종이 있는 경우만 연결합니다. 확인되지 않은 세부 기종은 미확인으로 둡니다.','기업 수는 종목코드로 중복 제거합니다. 회사별 수주잔고는 해당 장비 단독 수주가 아니라 기존 보고서의 회사·사업부문 기준입니다.'])
