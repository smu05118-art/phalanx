// EchoTik 샵 스냅샷 배치 수집 — echotik.live 로그인 세션(Enterprise)에서 in-page 실행.
// 사용: Chrome MCP javascript_tool 로 이 함수 붙여넣고 collectEchoTik(SHOPS) 실행 →
// 반환 JSON을 alt_browser_inject.py 로 주입(라벨=EchoTik…·브랜드).
//
// 각 샵을 상세 페이지로 열어 렌더 텍스트를 파싱(숫자 오프페이지 마스킹 회피).
// SHOPS = [{ent, brand, shop_id}] — shop_id는 echotik.live/shops/{id} 의 숫자.
async function collectEchoTik(SHOPS) {
  const parseNum = (s) => {
    if (!s) return null;
    const m = String(s).replace(/[$,\s]/g, '').match(/([\d.]+)([MKB])?/);
    if (!m) return null;
    return Math.round(parseFloat(m[1]) * ({ K: 1e3, M: 1e6, B: 1e9 }[m[2]] || 1));
  };
  const grab = (txt, label) => {
    // "6.95M\nTotal Sales" 같은 라벨-값 페어 추출
    const re = new RegExp('([\\d.,]+[MKB]?)\\s*\\n?\\s*' + label, 'i');
    const m = txt.match(re);
    return m ? parseNum(m[1]) : null;
  };
  const out = {};
  for (const s of SHOPS) {
    try {
      const html = await (await fetch(`/shops/${s.shop_id}`, { headers: { Accept: 'text/html' } })).text();
      const txt = html.replace(/<[^>]+>/g, ' ').replace(/&[a-z]+;/g, ' ');
      out[s.shop_id] = {
        ent: s.ent, brand: s.brand,
        total_sales: grab(txt, 'Total Sales'),
        total_gmv: grab(txt, 'Total GMV'),
        followers: grab(txt, 'Followers'),
        sales_inc_30d: grab(txt, 'Sales Increment'),
        gmv_inc_30d: grab(txt, 'Estimate GMV Increment'),
      };
    } catch (e) { out[s.shop_id] = { ent: s.ent, error: String(e) }; }
  }
  return out;  // 이 JSON을 복사 → echotik_inject.py 로 주입
}
// 예: 확인된 샵 (추가 브랜드 샵ID는 echotik.live/shops/{id} 상세 URL에서 확보)
// const SHOPS = [{ent:'APR', brand:'medicube', shop_id:'7495514739648989419'}];
// collectEchoTik(SHOPS)

// ── 검색 기반 배치 파서 ── echotik.live/shops 에서 검색창에 키워드 입력 후 이 함수 실행.
// 렌더된 Shops List 테이블 상위 행을 파싱해 브랜드 샵 지표 추출(숫자 마스킹 회피).
function parseShopRows() {
  const num = (s) => {
    if (!s) return null;
    const m = String(s).replace(/[$,\s]/g, '').match(/([\d.]+)([MKB])?/);
    return m ? Math.round(parseFloat(m[1]) * ({ K: 1e3, M: 1e6, B: 1e9 }[m[2]] || 1)) : null;
  };
  // 컬럼: 샵명 카테고리 평점 상품수 노출 평균가(₩) 7일판매 7일GMV(₩) 총판매 총GMV(₩) 인플루언서 영상 라이브
  return [...document.querySelectorAll('tr')]
    .map((tr) => tr.innerText.replace(/\n+/g, ' ').replace(/\s+/g, ' ').trim())
    .filter((t) => t.length > 30 && !/No of Products/.test(t))
    .map((t) => {
      // $금액(₩...) 페어를 순서대로: [0]=평균가 [1]=7일GMV [2]=총GMV
      const usd = [...t.matchAll(/\$([\d.]+[MKB]?)\s*\(￥/g)].map((m) => num(m[1]));
      // K/숫자 단독(판매/인플루언서 등)
      const name = t.split(/\s+(Beauty|Womenswear|Menswear|Health|Household|Food|Shoes|Luggage)/)[0].trim();
      return { name, avg_price: usd[0], gmv_7d: usd[1], total_gmv: usd[2], raw: t };
    });
}
// 사용: 검색 후 → parseShopRows() → 브랜드 맞는 행 선택 → echotik_shops.json 갱신 → echotik_inject.py
