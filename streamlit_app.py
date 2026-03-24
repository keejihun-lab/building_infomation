import streamlit as st
import sys
import ssl
import json
import urllib.request
from urllib.parse import urlencode, quote
from pathlib import Path

# 로컬 패키지 임포트 설정
APP_DIR = Path(__file__).parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from building_register.region import search_region_code

# --- 기본 상수 및 데이터 ---
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

# --- 유틸리티 함수 ---
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
    except Exception:
        return yyyymmdd

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
st.cache_data
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
st.title("🏠 인스타그램 매물 자동화 및 생성기")

# 세션 상태 초기화
if "bld_data" not in st.session_state:
    st.session_state.bld_data = {
        "area": "", "area_public": 0.0, "floor_no": "", "total_floors": "", 
        "use_date": "", "parking": "", "prop_type": "", "bld_name": "", "vln_yn": ""
    }

# 1. 사이드바 (중개사 정보 설정)
with st.sidebar:
    st.header("중개사 정보 설정")
    cfg_name = st.text_input("상호명", value="부경파트너공인중개사사무소")
    cfg_addr = st.text_input("소재지", value="부산시 남구 대연동 512-2 1층")
    cfg_phone = st.text_input("연락처", value="010-6402-2328")
    cfg_reg = st.text_input("등록번호", value="제26290-2022-00010호")
    cfg_agent = st.text_input("대표", value="이지훈")
    cfg_email = st.text_input("이메일", value="keejihun@nate.com")
    cfg_coverage = st.text_input("중개 범위", value="부산시 진구/남구/수영구")

# 2. 거래 조건 / 매물 정보
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("매물 주소 및 거래 조건")
    dong = st.selectbox("동 선택", ALL_DONGS, index=ALL_DONGS.index("광안동"))
    gu_list = BUSAN_DONG_TO_GU.get(dong, [])
    gu = st.selectbox("구 선택", gu_list, index=0) if gu_list else st.text_input("구 입력")
    
    col_addr1, col_addr2 = st.columns(2)
    jibeon = col_addr1.text_input("지번 (예: 190-19)")
    ho = col_addr2.text_input("호수 (예: 203)")
    bld_name_manual = st.text_input("건물명(별칭) 직접입력", value="")

    st.markdown("---")
    trade_type = st.radio("거래 형태", ["월세", "전세"], horizontal=True)
    deposit = st.number_input("보증금(만원)", min_value=0, value=0, step=100)
    monthly = 0
    if trade_type == "월세":
        monthly = st.number_input("월세(만원)", min_value=0, value=0, step=10)
    
    col_mgmt1, col_mgmt2 = st.columns([1, 2])
    mgmt = col_mgmt1.number_input("관리비(만원)", min_value=0, value=10, step=1)
    mgmt_rule = col_mgmt2.checkbox("관리규약에 따름")
    mgmt_detail = st.text_input("관리비 세부 내역", value=f"공용관리비 : {mgmt}만원 (관리 규약 따라 수도,전기,가스 별도)" if mgmt_rule else (f"공용관리비 : {mgmt-2}만원, 인터넷 2만원" if mgmt>=2 else "인터넷 포함"))

    st.markdown("---")
    col_etc1, col_etc2 = st.columns(2)
    rooms = col_etc1.text_input("방/욕실 수", value="1/1")
    elevator = col_etc2.text_input("엘리베이터(대)", value="1")
    movein_type = col_etc1.radio("입주날짜", ["즉시", "날짜지정"], horizontal=True)
    movein_date = col_etc2.text_input("날짜지정 (예: 2026-03-31)", disabled=(movein_type=="즉시"))
    
    direction = col_etc1.text_input("방향", value="동향")
    dir_std = col_etc2.radio("방향 기준", ["거실 기준", "안방 기준"], horizontal=True)

with col2:
    st.subheader("매물 상세 정보 (API)")
    
    if st.button("🔍 건축물대장 조회", type="primary"):
        if not jibeon:
            st.error("지번을 입력해주세요.")
        else:
            with st.spinner("건축물대장 조회 중..."):
                try:
                    res = fetch_building_info(dong, gu, jibeon, ho)
                    title_items = res.get("title_items", [])
                    expos_items = res.get("expos_items", [])
                    if not title_items:
                        st.error("❌ 해당 주소의 건축물대장 정보를 찾지 못했습니다.")
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
                                try: area_public += float(e.get("area", 0) or 0)
                                except: pass
                        if not area and expos_items and isinstance(expos_items[0], dict):
                            area = expos_items[0].get("area", "")
                            floor_no = expos_items[0].get("flrNo", "")
                        
                        if not floor_no: floor_no = guess_floor_from_ho(ho)
                        
                        st.session_state.bld_data = {
                            "area": str(area),
                            "area_public": f"{area_public:.2f}",
                            "floor_no": str(floor_no),
                            "total_floors": str(t.get("grndFlrCnt", "")),
                            "use_date": format_date(t.get("useAprDay", "")),
                            "parking": str(total_parking(t)),
                            "prop_type": str(expos_prop_type or t.get("mainPurpsCdNm", "")),
                            "bld_name": str(t.get("bldNm", "") or t.get("roadNmBldNm", "")),
                            "vln_yn": str(t.get("vlnBldYn", "")).strip().upper()
                        }
                        st.success(f"✅ 조회 완료 ({len(title_items)}건)")
                except Exception as e:
                    import traceback
                    st.error(f"오류가 발생했습니다: {e}\n{traceback.format_exc()}")
    
    bd = st.session_state.bld_data
    
    # API 연동 데이터 인풋창 (가져온 데이터로 자동완성 되지만 수동 수정도 가능하게 처리)
    v_area = st.text_input("전용면적(㎡)", value=bd["area"])
    v_area_public = st.text_input("공용면적(㎡)", value=bd["area_public"])
    v_floor = st.text_input("매물층수", value=bd["floor_no"])
    v_total_floors = st.text_input("건물 총 층수", value=bd["total_floors"])
    v_use_date = st.text_input("사용승인일", value=bd["use_date"])
    v_parking = st.text_input("총 주차대수(대)", value=bd["parking"])
    v_prop_type = st.text_input("매물종류", value=bd["prop_type"])
    
    is_vln = "위반건축물임" if bd["vln_yn"] == "Y" else ("해당없음" if bd["vln_yn"] == "N" else "미확인")
    st.info(f"**위반건축물 여부**: {is_vln}")
    
# 3. 텍스트 합성 
st.markdown("---")
st.subheader("게시글 미리보기")

if st.button("📝 게시글 텍스트 생성 (위 내용으로)"):
    def _area_line(excl, pub):
        if not excl: return "📐 전용면적  미확인"
        try:
            excl_f, pub_f = float(excl), float(pub)
            py = round((excl_f + pub_f) / 3.3, 2)
            return f"📐 전용면적  {excl}㎡ / 공용면적  {excl_f + pub_f:.2f}㎡ ({py}평)"
        except:
            return f"📐 전용면적  {excl}㎡"
            
    bun, ji = parse_jibeon(jibeon)
    bld_final = bld_name_manual or bd["bld_name"]
    
    addr = f"부산광역시 {gu} {dong} {bun}" + (f"-{ji}" if ji and ji not in ("0","") else "")
    if bld_final: addr += f', "{bld_final}"'
    
    movein_str = "즉시 입주 가능" if movein_type == "즉시" else (movein_date or "협의")
    
    if trade_type == "월세":
        price_str = f"💰 보증금  {format_money(deposit)} / 월세  {format_money(monthly)}"
    else:
        price_str = f"💰 전세  {format_money(deposit)}"
        
    mgmt_str = f"{mgmt}만원" + (f" (세부: {mgmt_detail})" if mgmt_detail else "") if mgmt > 0 else "없음"
    
    lines = [
        f"📞 {cfg_phone}",
        f"🏢 {cfg_name}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        price_str,
        f"🔑 관리비  {mgmt_str}",
        "",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"📍 {addr}",
        f"🏠 건물종류  {v_prop_type}  /  {trade_type}",
        _area_line(v_area, v_area_public),
        f"🏗️  층수  {v_floor}층/{v_total_floors}층",
        f"📅 사용승인일  {v_use_date}",
        f"🚗 주차  {v_parking}대" if v_parking else "🚗 주차  미확인",
        "⚠️ 이 세대는 위반건축물임" if bd["vln_yn"] == "Y" else "",
        f"🧭 방향  {direction} ({dir_std})" if direction else "",
        f"🛗 엘리베이터  {elevator}대",
        f"🛏️  방/욕실  {rooms}",
        f"📆 입주  {movein_str}",
        "━━━━━━━━━━━━━━━━━━━━━━",
        "",
        "⊙ 중개사 정보",
        f"  상호  {cfg_name}",
        f"  소재지  {cfg_addr}",
        f"  연락처  {cfg_phone}",
        f"  등록번호  {cfg_reg}",
        f"  대표  {cfg_agent}",
    ]
    if cfg_coverage:
        lines += ["", "━━━━━━━━━━━━━━━━━━━━━━", "▣ 매물 접수 및 중개 범위 ▣", "매수 / 매도 / 임대 / 전세", f"({cfg_coverage})"]
    if cfg_email:
        lines += ["", f"✉️  비즈니스 문의  {cfg_email}"]
        
    final_text = "\n".join(l for l in lines if l != "")
    st.text_area("인스타그램 글 복사 공간", value=final_text, height=500)
    st.success("게시글이 성공적으로 생성되었습니다. 위 창에서 복사(Ctrl+C, Cmd+C) 하세요.")
