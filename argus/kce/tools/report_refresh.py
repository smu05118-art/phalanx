"""DART 보고서 재확인 정책. 관측일과 조회일을 분리하고 원문·기존 유효 캐시를 보존한다."""
import datetime
import hashlib
import json
import os
from zoneinfo import ZoneInfo
from kce_lib import atomic_write


def today():
    return datetime.datetime.now(ZoneInfo('Asia/Seoul')).date()


def latest_candidate(day=None):
    """방금 종료한 달력 분기. 발표를 추정하지 않고 이 분기의 공개 여부만 조회한다."""
    day = day or today()
    y, q = day.year, (day.month - 1) // 3
    return '%dQ%d' % ((y, q) if q else (y - 1, 4))


def due(record, quarter, day=None):
    day = day or today()
    if not record:
        return True
    try:
        checked = datetime.date.fromisoformat(record.get('_refresh_checked_on', ''))
        latest = latest_candidate(day)
        distance = (int(latest[:4]) - int(quarter[:4])) * 4 + int(latest[-1]) - int(quarter[-1])
        ttl = 1 if distance <= 1 else 7
        return not 0 <= (day - checked).days < ttl
    except (ValueError, TypeError):
        return True


def read(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def receipt(record):
    return (record or {}).get('rcp') or (record or {}).get('rcpNo')


def window(quarter):
    """정정공시는 원래 접수 창 이후에도 온다. 해당 분기말 월부터 현재까지 조회한다."""
    y, q = int(quarter[:4]), int(quarter[-1])
    return '%d%02d01' % (y, q * 3), today().strftime('%Y%m%d')


def candidates(reports, quarter):
    """대상 기준월이 명시된 정기보고서만 최신 접수순으로 반환한다.

    종료 직후에는 이전 분기의 정정공시만 검색될 수 있다. 이를 새 분기로
    폴백하면 미공시 분기에 과거값이 들어가므로 기준월 불일치는 제외한다.
    """
    from kce_fetch import _REPORT_TITLE
    want = (quarter[:4], "%02d" % (int(quarter[-1]) * 3))
    matches = []
    for rcp, title in reports:
        found = _REPORT_TITLE.search(title or "")
        if found and (found.group(2), found.group(3)) == want:
            matches.append((rcp, title))
    return sorted(matches, key=lambda pair: pair[0], reverse=True)


def tracked_quarters(cache_root, stock, latest=None):
    """단일 분기 수집기도 최근 두 분기와 재확인 시점이 된 기존 기록을 조회한다."""
    import re
    latest = latest or latest_candidate()
    y, q = int(latest[:4]), int(latest[-1])
    previous = "%dQ%d" % ((y, q - 1) if q > 1 else (y - 1, 4))
    quarters = {latest, previous}
    folder = os.path.join(cache_root, stock)
    if os.path.isdir(folder):
        for name in os.listdir(folder):
            if re.fullmatch(r"\d{4}Q[1-4]\.json", name):
                quarter = name[:-5]
                if due(read(os.path.join(folder, name)), quarter):
                    quarters.add(quarter)
    return sorted(quarters, reverse=True)


def archive(path):
    """변경 전 원본 바이트를 내용 해시별로 보존한다(같은 바이트 중복 저장 없음)."""
    if not os.path.isfile(path):
        return
    with open(path, 'rb') as f:
        raw = f.read()
    folder = os.path.join(os.path.dirname(path), '_revisions')
    os.makedirs(folder, exist_ok=True)
    target = os.path.join(folder, os.path.basename(path) + '.' + hashlib.sha256(raw).hexdigest()[:16])
    if not os.path.isfile(target):
        atomic_write(target, raw.decode('utf-8'))


def save(path, record):
    """새 유효 관측은 이력을 남기고 교체. 실패 관측은 기존 유효값을 덮지 않는다."""
    previous = read(path)
    if previous and previous.get('ok') and not record.get('ok'):
        return False
    out = dict(record, _refresh_checked_on=today().isoformat())
    if previous and receipt(previous) != receipt(out):
        archive(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    atomic_write(path, json.dumps(out, ensure_ascii=False, indent=1) + '\n')
    record.update({'_refresh_checked_on': out['_refresh_checked_on']})
    return True


def checked(path, record):
    """접수번호가 같다는 확인일만 갱신한다. 관측분기·값·공시일은 그대로 둔다."""
    save(path, record)
    return record
