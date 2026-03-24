import streamlit as st
import sys
import ssl
import json
import urllib.request
from urllib.parse import urlencode, quote
from pathlib import Path

# Import local modules
APP_DIR = Path(__file__).parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

try:
    from building_register.region import search_region_code
except ImportError:
    st.error("Error: 'building_register' folder not found. Please upload the entire folder to GitHub.")
    st.stop()

# --- Constant & Data ---
API_KEY = "2d5bf447007714bfd2519b0a0c9d754c46d6da3ceccdb9adb046bcdc5ecc402f"
BASE_URL = "https://apis.data.go.kr/1613000/BldRgstHubService"

BUSAN_DONG_TO_GU = {
    "중앙동": ["중구"], "동광동": ["중구"], "대청동": ["중구"], "보수동": ["중구"], "부평동": ["중구"], "광복동": ["중구"], "남포동": ["중구"], "영주동": ["중구"],
    "동대신동": ["서구"], "서대신동": ["서구"], "부민동": ["서구"], "아미동": ["서구"], "초장동": ["서구"], "충무동": ["서구"], "남부민동": ["서구"], "암남동": ["서구"],
    "초량동": ["동구"], "수정동": ["동구"], "좌천동": ["동구"], "범일동": ["동구"],
    "남항동": ["영도구"], "영선동": ["영도구"], "신선동": ["영도구"], "봉래동": ["영도구"], "청학동": ["영도구"], "동삼동": ["영도구"],
    "부전동": ["부산진구"], "범전동": ["부산진구"], "연지동": ["부산진구"], "초읍동": ["부산진구"], "양정동": ["부산진구"], "전포동": ["부산진구"], "부암동": ["부산진구"], "당감동": ["부산진구"], "개금동": ["부산진구"], "가야동": ["부산진구"],
    "수안동": ["동래구"], "낙민동": ["동래구"], "복천동": ["동래구"], "안락동": ["동래구"], "명륜동": ["동래구"], "사직동": ["동래구"], "칠산동": ["동래구"], "온천동": ["동래구", "금정구"], "거제동": ["동래구", "연제구"], "연산동": ["동래구", "연제구"],
    "대연동": ["남구"], "용호동": ["남구"], "용당동": ["남구"], "감만동": ["남구"], "우암동": ["남구"], "문현동": ["남구"],
    "구포동": ["북구"], "금곡동": ["북구"], "화명동": ["북구"], "덕천동": ["북구"], "만덕동": ["북구"],
    "우동": ["해운대구"], "중동": ["해운대구"], "좌동": ["해운대구"], "송정동": ["해운대구"], "반송동": ["해운대구"], "재송동": ["해운대구"],
    "괴정동": ["사하구"], "당리동": ["사하구"], "하단동": ["사하구"], "신평동": ["사하구"], "장림동": ["사하구"], "다대동": ["사하구"], "구평동": ["사하구"], "감천동": ["사하구"],
    "서동": ["금정구"], "금사동": ["금정구"], "부곡동": ["금정구"], "장전동": ["금정구"], "구서동": ["금정구"], "금성동": ["금정구"], "청룡동": ["금정구"], "남산동": ["금정구"], "두구동": ["금정구"],
    "대저1동": ["강서구"], "대저2동": ["강서구"], "강동동": ["강서구"], "명지동": ["강서구"], "가락동": ["강서구"], "녹산동": ["강서구"], "가덕도동": ["강서구"],
    "토곡동": ["연제구"], "황령동": ["연제구"],
    "광안동": ["수영구"], "남천동": ["수영구"], "민락동": ["수영구"], "망미동": ["수영구"], "수영동": ["수영구"],
    "삼락동": ["사상구"], "모라동": ["사상구"], "덕포동": ["사상구"], "괘법동": ["사상구"], "감전동": ["사상구"], "주례동": ["사상구"], "학장동": ["사상구"], "엄궁동": ["사상구"],
    "기장읍": ["기장군"], "장안읍": ["기장군"], "정관읍": ["기장군"], "일광읍": ["기장군"], "철마면": ["기장군"],
}
ALL_DONGS = sorted(BUSAN_DONG_TO_GU.keys())

# --- Utilities ---
def format_money(man_won: int) -> str:
    if man_won <= 0: return "0원"
    uk = man_won // 10000
    rem = man_won % 10000
    parts = []
    if uk: parts.append(f"{uk}억")
    if rem: parts.append(f"{rem}만원")
    elif uk: parts.append("원")
    return " ".join(parts) if parts else "0원"

def format_date(yyyymmdd: str) -> str:
    if not yyyymmdd or len(yyyymmdd) < 8: return yyyymmdd or ""
    try:
        y, m, d = int(yyyymmdd[:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:8])
        return f"{y}년 {m}월 {d}일"
    except Exception: return yyyymmdd

def guess_floor_from_ho(ho: str) -> str:
    digits = "".join(c for c in ho if c.isdigit())
    if len(digits) >= 3:
        try: return str(int(digits[:-2]))
        except: pass
    return "?"

def parse_jibeon(jibeon: str) -> tuple[str, str]:
    jibeon = jibeon.strip()
    if "-" in jibeon:
        parts = jibeon.split("-", 1)
        return parts[0].strip(), parts[1].strip() or "0"
    return jibeon, "0"

def total_parking(item: dict) -> int:
    return (int(item.get("indrMechUtcnt") or 0) + int(item.get("indrAutoUtcnt") or 0) +
            int(item.get("oudrMechUtcnt") or 0) + int(item.get("oudrAutoUtcnt") or 0))

# --- API 연동 함수 ---
@st.cache_data
def fetch_building_info(dong: str, gu: str, jibeon: str, ho: str):
    bun, ji = parse_jibeon(jibeon)
    region_query = f"부산광역시 {gu} {dong}"
    region = search_region_code(region_query)
    if "error" in region:
        raise ValueError(f"지역 코드 조회 실패: {region.get('message')}")

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    def _call(endpoint: str, params: dict):
        base = {"serviceKey": API_KEY, "_type": "json", "numOfRows": "50", "pageNo": "1"}
        base.update({k: str(v) for k, v in params.items() if v is not None and str(v).strip() != ""})
        qs = urlencode(base, safe="%+=", quote_via=quote)
        req = urllib.request.Request(f"{BASE_URL}/{endpoint}?{qs}", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            body = json.loads(resp.read().decode()).get("response", {}).get("body", {})
        items_raw = body.get("items", {})
        if isinstance(items_raw, dict):
            items = items_raw.get("item", [])
        else:
            items = []
        return [items] if isinstance(items, dict) else items

    base_params = {"sigunguCd": region["sigungu_cd"], "bjdongCd": region["bjdong_cd"], 
                   "bun": bun.zfill(4) if bun else None, "ji": ji.zfill(4) if ji and ji not in ("0","") else "0000"}

    title_items = _call("getBrTitleInfo", base_params)
    
    ho_clean = ho.strip().rstrip("호") if ho else ""
    expos_params = {**base_params, "hoNm": ho_clean} if ho_clean else base_params
    expos_items = _call("getBrExposPubuseAreaInfo", expos_params)

    if ho_clean and expos_items:
        filtered = [e for e in expos_items if str(e.get("hoNm", "")).strip().rstrip("호") == ho_clean]
        if filtered: expos_items = filtered

    return {"region": region, "title_items": title_items, "expos_items": expos_items}

# --- 메인 앱 ---
st.set_page_config(page_title="인스타그램 매물 생성기", page_icon="🏠", layout="wide")
st.markdown("<h2 style='text-align: center; color: #1E3A8A; margin-top: -1rem;'>🏠 인스타그램 매물 자동 생성기 (Web Ver.)</h2>", unsafe_allow_html=True)

# CSS for compact layout
st.markdown("""
    <style>
    .stTabs [data-baseweb="tab-list"] button [data-testid="stMarkdownContainer"] p { font-size: 1.1rem; font-weight: bold; }
    .block-container { padding-top: 1.5rem; padding-bottom: 0rem; max-width: 95%; }
    div[data-testid="stVerticalBlock"] > div { margin-top: -0.7rem; }
    .stTextInput > div > div > input { padding-top: 5px; padding-bottom: 5px; }
    div[data-testid="stExpander"] { margin-bottom: 0.5rem; }
    </style>
    """, unsafe_allow_html=True)

# 세션 상태 초기화
if "bld_data" not in st.session_state:
    st.session_state.bld_data = {
        "area": "", "area_public": "0.00", "floor_no": "", "total_floors": "", 
        "use_date": "", "parking": "", "prop_type": "", "bld_name": "", "vln_yn": ""
    }
if "generate_post" not in st.session_state:
    st.session_state.generate_post = False

tab_listing, tab_agent = st.tabs(["  🏢 매물 정보 입력  ", "  👤 중개사 정보 설정  "])

with tab_agent:
    st.markdown("### 【 ⚙️ 공인중개사 정보 설정 】")
    cfg_name = st.text_input("상호명 *", value="부경파트너공인중개사사무소", key="cfg_name")
    cfg_addr = st.text_input("소재지 *", value="부산시 남구 대연동 512-2 1층", key="cfg_addr")
    cfg_phone = st.text_input("연락처 *", value="010-6402-2328", key="cfg_phone")
    cfg_reg = st.text_input("등록번호", value="제26290-2022-00010호", key="cfg_reg")
    cfg_agent_name = st.text_input("대표자 성명", value="이지훈", key="cfg_agent_name")
    cfg_email = st.text_input("이메일", value="keejihun@nate.com", key="cfg_email")
    cfg_coverage = st.text_input("중개 가능 지역", value="부산시 진구/남구/수영구", key="cfg_coverage")

with tab_listing:
    # 3컬럼으로 분할하여 한 화면에 배치 (1, 1, 1.4 비율)
    col1, col2, col3 = st.columns([1, 1, 1.4])

    with col1:
        st.caption("📍 【 주소 및 거래 조건 】")
        dong = st.selectbox("동 *", ALL_DONGS, index=ALL_DONGS.index("광안동"), key="sb_dong")
        gu_list = BUSAN_DONG_TO_GU.get(dong, [])
        gu = st.selectbox("구", gu_list, index=0, key="sb_gu") if gu_list else st.text_input("구 입력", key="ti_gu")
        
        ca1, ca2 = st.columns(2)
        jibeon = ca1.text_input("지번 *", placeholder="123-45", key="ti_jibeon")
        ho = ca2.text_input("호수 *", placeholder="203", key="ti_ho")
        bld_name_manual = st.text_input("건물명(수정)", value="", placeholder="수동 입력 또는 조회 시 자동", key="ti_bld_name_manual")

        trade_type = st.radio("거래형태 *", ["월세", "전세"], horizontal=True, key="rb_trade_type")
        ct1, ct2 = st.columns(2)
        deposit = ct1.number_input("보증금(만원) *", min_value=0, value=0, step=100, key="ni_deposit")
        monthly = 0
        if trade_type == "월세":
            monthly = ct2.number_input("월세(만원)", min_value=0, value=0, step=10, key="ni_monthly")
        
        mgmt = st.number_input("관리비(만원)", min_value=0, value=10, key="ni_mgmt")
        mgmt_rule = st.checkbox("관리규약에 따름", value=True, key="cb_mgmt_rule")
        mgmt_detail = st.text_area("관리비 세부 내역", 
                                  value=f"공용관리비 : {mgmt}만원 (관리 규약 따라 수도,전기,가스 별도)" if mgmt_rule else (f"공용관리비 : {mgmt-2}만원, 인터넷 2만원" if mgmt>=2 else "인터넷 포함"),
                                  height=68, key="ta_mgmt_detail")

    with col2:
        st.caption("📋 【 매물 상세 / 기타 】")
        bd = st.session_state.bld_data
        
        v_area = st.text_input("전용면적(㎡)", value=bd["area"], help="조회 시 자동 입력", key="ti_v_area")
        v_area_public = st.text_input("공용면적(㎡)", value=bd["area_public"], key="ti_v_area_public")
        
        cf1, cf2 = st.columns(2)
        v_floor = cf1.text_input("매물층수", value=bd["floor_no"], key="ti_v_floor")
        v_total_floors = cf2.text_input("건물의 총 층수", value=bd["total_floors"], key="ti_v_total_floors")
        
        v_use_date = st.text_input("사용승인일", value=bd["use_date"], key="ti_v_use_date")
        v_parking = st.text_input("총 주차대수(대)", value=bd["parking"], key="ti_v_parking")
        v_prop_type = st.text_input("매물종류", value=bd["prop_type"], key="ti_v_prop_type")
        
        st.write("입주날짜")
        ce1, ce2 = st.columns([1, 2])
        movein_type = ce1.radio("입주날짜선택", ["즉시", "지정"], horizontal=True, label_visibility="collapsed", key="rb_movein_type")
        movein_date = ce2.text_input("지정일", value="2026-03-31", disabled=(movein_type=="즉시"), label_visibility="collapsed", key="ti_movein_date")
        
        cr1, cr2 = st.columns(2)
        rooms = cr1.text_input("방/욕실 개수", value="1/1", key="ti_rooms")
        elevator = cr2.text_input("엘리베이터 유무/대수", value="1대", key="ti_elevator")
        
        st.write("방향")
        cd1, cd2 = st.columns([1, 2])
        direction = cd1.text_input("방향", value="동향", label_visibility="collapsed", key="ti_direction")
        dir_std = cd2.selectbox("방향 기준", ["거실 기준", "안방 기준"], label_visibility="collapsed", key="sb_dir_std")
        
        is_vln = "⚠️ 위반건축물" if bd["vln_yn"] == "Y" else ("✅ 위반사항 없음" if bd["vln_yn"] == "N" else "❔ 위반 여부 미확인")
        st.info(is_vln)

    with col3:
        st.caption("📝 【 결과 미리보기 및 복사 】")
        
        if st.button("🔍 건축물대장 정보 조회", use_container_width=True, icon="🔎"):
            if not jibeon:
                st.error("지번을 입력해주세요.")
            else:
                with st.spinner("API 조회 대기 중..."):
                    try:
                        res = fetch_building_info(dong, gu, jibeon, ho)
                        title_items = res.get("title_items", [])
                        expos_items = res.get("expos_items", [])
                        if not title_items:
                            st.warning("❌ 건축물대장 정보를 찾을 수 없습니다.")
                        else:
                            t = title_items[0]
                            area, area_public, floor_no, expos_prop_type = "", 0.0, "", ""
                            for e in expos_items:
                                if not isinstance(e, dict): continue
                                gb_cd, gb_nm = str(e.get("exposPubuseGbCd", "")), str(e.get("exposPubuseGbCdNm", ""))
                                if gb_cd == "1" or "전유" in gb_nm:
                                    if not area:
                                        area = e.get("area", "")
                                        floor_no = e.get("flrNo", "")
                                        expos_prop_type = e.get("mainPurpsCdNm", "")
                                else:
                                    try: 
                                        val = float(e.get("area", 0) or 0)
                                        area_public += val
                                    except: pass
                            if not area and expos_items and isinstance(expos_items[0], dict):
                                area = expos_items[0].get("area", "")
                                floor_no = expos_items[0].get("flrNo", "")
                            if not floor_no: floor_no = guess_floor_from_ho(ho)
                            
                            st.session_state.bld_data = {
                                "area": str(area), "area_public": f"{area_public:.2f}",
                                "floor_no": str(floor_no), "total_floors": str(t.get("grndFlrCnt", "")),
                                "use_date": format_date(t.get("useAprDay", "")), "parking": str(total_parking(t)),
                                "prop_type": str(expos_prop_type or t.get("mainPurpsCdNm", "")),
                                "bld_name": str(t.get("bldNm", "") or t.get("roadNmBldNm", "")),
                                "vln_yn": str(t.get("vlnBldYn", "")).strip().upper()
                            }
                            st.rerun()
                    except Exception as e:
                        st.error(f"⚠️ API 호출 오류: {e}")

        if st.button("🚀 인스타그램 게시글 생성", use_container_width=True, type="primary", icon="✨"):
            st.session_state.generate_post = True

        def _get_area_line(excl, pub):
            if not excl: return "📐 전용면적  미확인"
            try:
                excl_f = float(excl)
                pub_f = float(pub or 0)
                tot_f = excl_f + pub_f
                py_f = tot_f / 3.3
                py_s = f"{py_f:.2f}"
                return f"📐 전용면적  {excl}㎡ / 공용면적  {tot_f:.2f}㎡ ({py_s}평)"
            except:
                return f"📐 전용면적  {excl}㎡"
        
        final_text = ""
        if st.session_state.generate_post:
            b_clean, j_clean = parse_jibeon(jibeon or "")
            b_name = bld_name_manual or bd["bld_name"]
            addr = f"부산 {gu} {dong} {b_clean}" + (f"-{j_clean}" if j_clean and j_clean != "0" else "")
            if b_name: addr += f' ("{b_name}")'
            
            mv_str = "즉시 입주" if movein_type == "즉시" else (movein_date or "협의")
            price_str = f"💰 보증금  {format_money(deposit)} / 월세  {format_money(monthly)}" if trade_type == "월세" else f"💰 전세  {format_money(deposit)}"
            m_str = f"{mgmt}만원" + (f" ({mgmt_detail})" if mgmt_detail else "") if mgmt > 0 else "없음"
            
            p_lines = [
                f"📞  {cfg_phone}", f"🏢  {cfg_name}", "━━━━━━━━━━━━━━━━━━━━━━", "",
                price_str, f"🔑  관리비  {m_str}", "", "━━━━━━━━━━━━━━━━━━━━━━",
                f"📍  {addr}", f"🏠  매물종류  {v_prop_type or '미확인'} ({trade_type})",
                _get_area_line(v_area, v_area_public),
                f"🏗️  층수  {v_floor}층 / {v_total_floors}층",
                f"📅  사용승인일  {v_use_date or '미확인'}",
                f"🚗  주차  {v_parking}대" if v_parking else "🚗  주차  미확인",
                "⚠️  위반건축물 여부: 이 세대는 위반건축물임" if bd["vln_yn"] == "Y" else "",
                f"🧭  방향  {direction} ({dir_std})" if direction else "",
                f"🛗  엘리베이터  {elevator}", f"🛏️  방/욕실  {rooms}",
                f"📆  입주  {mv_str}", "━━━━━━━━━━━━━━━━━━━━━━", "",
                "⊙ 중개사 정보", f"  상호: {cfg_name}", f"  소재지: {cfg_addr}",
                f"  연락처: {cfg_phone}", f"  등록번호: {cfg_reg}", f"  대표: {cfg_agent_name}",
            ]
            if cfg_coverage: p_lines += ["", "━━━━━━━━━━━━━━━━━━━━━━", "▣ 매물 접수 및 중개 범위 ▣", "매수 / 매도 / 임대 / 전세", f"({cfg_coverage})"]
            if cfg_email: p_lines += ["", f"✉️  비즈니스 문의  {cfg_email}"]
            
            final_text = "\n".join(l for l in p_lines if l != "")
        
        st.text_area("결과 (아래를 클릭하여 전체 복사)", value=final_text or "버튼을 누르면 글이 생성됩니다.", height=480)
        if final_text:
            st.caption("💡 팁: 텍스트 영역을 클릭한 뒤 Ctrl+A(또는 Cmd+A) 후 Ctrl+C(또는 Cmd+C) 하세요.")
