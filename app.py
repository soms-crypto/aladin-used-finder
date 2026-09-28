import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
from collections import defaultdict

# 페이지 기본 설정
st.set_page_config(
    page_title="알라딘 중고 묶음배송 검색기",
    page_icon="📚",
    layout="wide"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.aladin.co.kr/",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
}

OFFCODE_MAP = {
    "gangnam": "강남점", "sinchon": "신촌점", "jongno": "종로점", "jamsil": "잠실점",
    "jamsiltower": "잠실롯데월드타워점", "hapjeong": "합정점", "daehakro": "대학로점",
    "nowon": "노원점", "suyu": "수유점", "yeongdeungpo": "영등포점", "geondae": "건대점",
    "sillim": "신림점", "mokdong": "목동점", "gasan": "가산점", "songpa": "송파점",
    "bucheon": "부천점", "ilsan": "일산점", "ilsan_wd": "일산웨스턴돔점", "seohyeon": "분당서현점",
    "yatap": "분당야탑점", "suwon": "수원점", "suwonsi": "수원시청점", "pyeongchon": "평촌점",
    "anyang": "안양점", "guwol": "인천구월점", "songdo": "인천송도점", "uijeongbu": "의정부점",
    "dongtan": "동탄점", "guri": "구리점", "daejeon": "대전은행점", "daejeonsi": "대전시청점",
    "cheonan": "천안신부점", "cheongju": "청주성안길점", "seomyeon": "부산서면점",
    "centum": "부산센텀점", "ksu": "부산경성대점", "dongseongro": "대구동성로점",
    "sangin": "대구상인점", "ulsan": "울산점", "changwon": "창원점", "pohang": "포항점",
    "chungjangro": "광주충장로점", "sangmu": "광주상무점", "jeonju": "전주점", "jeju": "제주점"
}

def fetch_soup(url, params=None):
    try:
        resp = requests.get(url, headers=HEADERS, params=params, timeout=10)
        raw = resp.content
        if b'charset=euc-kr' in raw.lower() or b'charset="euc-kr"' in raw.lower():
            encoding = 'euc-kr'
        elif b'charset=utf-8' in raw.lower() or b'charset="utf-8"' in raw.lower():
            encoding = 'utf-8'
        else:
            encoding = resp.apparent_encoding or 'utf-8'

        try:
            html = raw.decode(encoding)
        except Exception:
            try:
                html = raw.decode('utf-8')
            except Exception:
                html = raw.decode('euc-kr', errors='replace')
        return BeautifulSoup(html, 'html.parser')
    except Exception:
        return None

def fetch_aladin_candidates(query, max_candidates=5):
    clean_query = query.strip()
    is_digit_isbn = bool(re.fullmatch(r"\d{10,13}", clean_query))

    params = {"SearchWord": clean_query, "SearchTarget": "Book"}
    soup = fetch_soup("https://www.aladin.co.kr/search/wsearchresult.aspx", params=params)
    items = soup.select(".ss_book_box") if soup else []

    if not items:
        params["SearchTarget"] = "All"
        soup = fetch_soup("https://www.aladin.co.kr/search/wsearchresult.aspx", params=params)
        items = soup.select(".ss_book_box") if soup else []

    if not items:
        return []

    candidates = []
    query_no_space = clean_query.replace(" ", "").lower()

    for item in items:
        title_elem = item.select_one("a.bo3")
        if not title_elem:
            continue

        title = title_elem.get_text(strip=True)
        href = title_elem.get("href", "")
        match = re.search(r"ItemId=(\d+)", href)
        item_id = match.group(1) if match else None
        if not item_id:
            continue

        title_no_space = title.replace(" ", "").lower()
        clean_title = re.sub(r'\(.*?\)|\[.*?\]', '', title).strip()
        clean_title_no_space = clean_title.replace(" ", "").lower()

        match_tier = 0
        if is_digit_isbn:
            match_tier = 3
        else:
            if query_no_space not in title_no_space:
                continue
            if clean_title_no_space == query_no_space:
                match_tier = 3
            elif clean_title_no_space.startswith(query_no_space):
                match_tier = 2
            else:
                match_tier = 1

        sub_info = "상세 정보 없음"
        for li in item.select("li"):
            txt = li.get_text(" ", strip=True)
            if any(k in txt for k in ["지은이", "옮긴이", "|"]) and "원" not in txt:
                sub_info = txt
                break

        sales_point_num = 0
        sales_point_text = ""
        for li in item.select("li"):
            txt = li.get_text(" ", strip=True)
            if "세일즈포인트" in txt or "Sales Point" in txt:
                sp_match = re.search(r"(?:세일즈포인트|Sales Point)\s*[:：]?\s*([\d,]+)", txt)
                if sp_match:
                    sales_point_num = int(sp_match.group(1).replace(",", ""))
                    sales_point_text = f"세일즈포인트: {sales_point_num:,}"
                break

        candidates.append({
            "title": title,
            "item_id": item_id,
            "sub_info": sub_info,
            "sales_point": sales_point_text,
            "sp_num": sales_point_num,
            "tier": match_tier
        })

    if not candidates:
        return []

    candidates.sort(key=lambda x: (x["tier"], x["sp_num"]), reverse=True)
    return candidates[:max_candidates]

def parse_seller_info(seller_td):
    text = seller_td.get_text(" ", strip=True)
    seller_url = ""

    if ("알라딘" in text and ("직배송" in text or "직접" in text)) and ("점" not in text):
        return "알라딘 직배송", "알라딘 본사(직배송)", "https://www.aladin.co.kr/home/wusedshopmain.aspx"

    store_links = seller_td.find_all("a", href=re.compile(r"usedstore|offcode", re.I))
    if bool(store_links) or ("우주점" in text) or ("중고매장" in text):
        branch_name = ""
        for a in store_links:
            href = a.get("href", "")
            if not seller_url and href:
                seller_url = requests.compat.urljoin("https://www.aladin.co.kr", href)
            txt = a.get_text(strip=True)
            clean_txt = re.sub(r"알라딘\s*(중고서점|중고매장)?\s*|[\[\]\(\)]", "", txt).strip()
            if clean_txt.endswith("점") and clean_txt != "우주점":
                branch_name = clean_txt
                break
            m = re.search(r"([가-힣A-Za-z0-9]+점)", clean_txt)
            if m and m.group(1) != "우주점":
                branch_name = m.group(1)
                break

        if not branch_name:
            cands = [w for w in re.findall(r"([가-힣A-Za-z0-9]+점)", text) if w not in ["우주점", "중고매장점", "매장점", "특약점"]]
            if cands:
                branch_name = cands[0]

        if not branch_name and seller_url:
            code_match = re.search(r"offcode=([a-zA-Z0-9_]+)", seller_url, re.I)
            if code_match:
                branch_name = OFFCODE_MAP.get(code_match.group(1).lower(), f"{code_match.group(1)}점")

        if not branch_name or branch_name == "우주점":
            branch_name = "지점확인필요"

        if not seller_url:
            seller_url = "https://www.aladin.co.kr/usedstore/wstoremain.aspx"
        return "광활한 우주점", f"우주점 ({branch_name})", seller_url

    for a in seller_td.find_all("a"):
        txt = a.get_text(strip=True)
        href = a.get("href", "")
        if txt and not any(k in txt for k in ["전문셀러", "개인셀러", "파워셀러", "상세보기", "만족도", "평가"]):
            if not re.search(r"[\d,]+원?", txt):
                if href:
                    seller_url = requests.compat.urljoin("https://www.aladin.co.kr", href)
                return "개인 판매자", txt, seller_url

    for string in seller_td.stripped_strings:
        s = string.strip()
        if any(bad in s for bad in ["전문셀러", "개인셀러", "파워셀러", "만족도", "배송비", "★", "☆"]):
            continue
        if re.search(r"^[\d,]+원?$", s):
            continue
        if len(s) >= 1:
            return "개인 판매자", s, ""

    return "개인 판매자", "일반 회원", ""

def collect_aladin_used_items(item_id, book_title, max_items=50):
    results = []
    seen = set()
    page = 1

    while len(results) < max_items:
        url = f"https://www.aladin.co.kr/shop/UsedShop/wuseditemall.aspx?ItemId={item_id}&TabType=0&page={page}"
        soup = fetch_soup(url)
        if not soup:
            break

        rows = soup.find_all("tr")
        page_results = []
        for row in rows:
            if row.find("tr"):
                continue
            tds = row.find_all("td")
            if len(tds) < 3:
                continue

            grade_idx = -1
            quality = "미표기"
            for i, td in enumerate(tds):
                txt = td.get_text(strip=True)
                m = re.fullmatch(r"\[?(최상\vert{}상\vert{}중\vert{}하)\]?", txt)
                if m:
                    grade_idx = i
                    quality = m.group(1)
                    break

            price_td = None
            seller_td = None

            if grade_idx != -1 and grade_idx + 2 < len(tds):
                candidate_price_td = tds[grade_idx + 1]
                if re.search(r"[\d,]+원", candidate_price_td.get_text()):
                    price_td = candidate_price_td
                    seller_td = tds[grade_idx + 2]

            if not price_td:
                for i, td in enumerate(tds):
                    txt = td.get_text(" ", strip=True)
                    if re.search(r"[\d,]+원", txt) and ("배송비" in txt or "할인" in txt):
                        price_td = td
                        if i + 1 < len(tds):
                            seller_td = tds[i + 1]
                        break

            if not price_td or not seller_td:
                continue

            seller_type, seller_name, seller_url = parse_seller_info(seller_td)
            price_text = price_td.get_text(" ", strip=True)
            all_prices = [int(p.replace(",", "")) for p in re.findall(r"([\d,]+)\s*원", price_text)]
            book_price = all_prices[0] if all_prices else 0

            if book_price > 0:
                page_results.append({
                    "도서명": book_title,
                    "판매처 유형": seller_type,
                    "판매처/매장명": seller_name,
                    "판매처링크": seller_url,
                    "도서가격(원)": book_price
                })

        if not page_results:
            break

        added = 0
        for item in page_results:
            key = (item["판매처/매장명"], item["도서가격(원)"])
            if key not in seen:
                seen.add(key)
                results.append(item)
                added += 1
                if len(results) >= max_items:
                    break
        if added == 0:
            break

        page += 1
        time.sleep(0.3)

    return results[:max_items]

# ================= UI 레이아웃 =================
st.title("📚 알라딘 중고 묶음배송 최적화 검색기")
st.markdown("도서를 검색해 판본을 장바구니에 담은 뒤 **묶음 배송 분석**을 실행하세요. 가장 많은 책을 보유한 판매처 순으로 정렬됩니다.")

if "cart" not in st.session_state:
    st.session_state.cart = []
if "candidates" not in st.session_state:
    st.session_state.candidates = []

col1, col2 = st.columns([1.2, 1])

with col1:
    st.subheader("1. 도서 검색 및 판본 선택")
    search_query = st.text_input("도서명 또는 13자리 ISBN", placeholder="예: 이방인, 월든, 9788937462665")
    
    if st.button("🔍 판본 검색", type="secondary"):
        if search_query.strip():
            with st.spinner("알라딘 판본 검색 중..."):
                cands = fetch_aladin_candidates(search_query, max_candidates=5)
                st.session_state.candidates = cands
                if not cands:
                    st.warning("일치하는 도서를 찾지 못했습니다.")
        else:
            st.info("검색어를 입력해 주세요.")

    if st.session_state.candidates:
        options = [
            f"[{i+1}] {c['title']} | {c['sub_info']} ({c['sales_point']})"
            for i, c in enumerate(st.session_state.candidates)
        ]
        selected_option = st.radio("추가할 판본을 선택하세요 (상위 5개)", options, index=0)

        if st.button("➕ 장바구니에 담기", type="primary"):
            sel_idx = int(selected_option.split("]")[0].replace("[", "")) - 1
            chosen_book = st.session_state.candidates[sel_idx]
            
            if any(b["item_id"] == chosen_book["item_id"] for b in st.session_state.cart):
                st.warning("이미 장바구니에 추가된 도서입니다.")
            else:
                st.session_state.cart.append(chosen_book)
                st.success(f"'{chosen_book['title']}' 등록 완료!")
                st.rerun()

with col2:
    st.subheader(f"2. 담긴 도서 목록 ({len(st.session_state.cart)}권)")
    
    if st.session_state.cart:
        for idx, book in enumerate(st.session_state.cart):
            st.markdown(f"**{idx+1}. {book['title']}** (ItemId: `{book['item_id']}`)")
        
        btn_c1, btn_c2 = st.columns(2)
        with btn_c1:
            run_analysis = st.button("🚀 묶음 배송 분석 시작", type="primary", use_container_width=True)
        with btn_c2:
            if st.button("🗑️ 전체 비우기", use_container_width=True):
                st.session_state.cart = []
                st.session_state.candidates = []
                st.rerun()
    else:
        st.info("장바구니가 비어 있습니다. 왼쪽에서 도서를 검색해 추가해 주세요.")
        run_analysis = False

# ================= 분석 결과 영역 =================
if run_analysis and st.session_state.cart:
    st.divider()
    st.subheader("📊 묶음 배송 분석 결과 (보유 권수 1순위)")
    
    progress_bar = st.progress(0)
    seller_stock = defaultdict(dict)
    seller_urls = {}
    
    total_books = len(st.session_state.cart)
    for idx, book in enumerate(st.session_state.cart):
        with st.spinner(f"[{idx+1}/{total_books}] '{book['title']}' 중고 매물 수집 중..."):
            items = collect_aladin_used_items(book["item_id"], book["title"], max_items=50)
            for it in items:
                key = (it["판매처 유형"], it["판매처/매장명"])
                b_title = it["도서명"]
                price = it["도서가격(원)"]

                if key not in seller_urls and it["판매처링크"]:
                    seller_urls[key] = it["판매처링크"]
                if b_title not in seller_stock[key] or price < seller_stock[key][b_title]:
                    seller_stock[key][b_title] = price
            progress_bar.progress((idx + 1) / total_books)
            time.sleep(0.4)

    summary_list = []
    for (s_type, s_name), books_dict in seller_stock.items():
        count = len(books_dict)
        # 줄바꿈과 가격을 포함한 도서 목록 생성
        book_lines = [f"• {title} ({price:,}원)" for title, price in books_dict.items()]
        book_list_html = "<br>".join(book_lines)
        
        total_book_price = sum(books_dict.values())
        link_url = seller_urls.get((s_type, s_name), "")

        if link_url:
            seller_display = f'<a href="{link_url}" target="_blank" style="color: #4da6ff; font-weight: bold; text-decoration: underline;">{s_name} ↗</a>'
        else:
            seller_display = s_name

        summary_list.append({
            "판매처 유형": s_type,
            "판매처/매장명": seller_display,
            "보유 권수": count,
            "보유 도서 목록": book_list_html,
            "도서 가격 합계": f"<b>{total_book_price:,}원</b>",
            "정렬용_합계": total_book_price
        })

    if not summary_list:
        st.warning("등록된 중고 매물을 찾을 수 없습니다.")
    else:
        df = pd.DataFrame(summary_list)
        df_sorted = df.sort_values(
            by=["보유 권수", "정렬용_합계"],
            ascending=[False, True]
        ).reset_index(drop=True)

        df_sorted.insert(0, "우선순위", range(1, len(df_sorted) + 1))
        df_sorted["보유율"] = df_sorted["보유 권수"].apply(lambda x: f"<b>{x}/{total_books}권</b>")

        cols = ["우선순위", "판매처 유형", "판매처/매장명", "보유율", "도서 가격 합계", "보유 도서 목록"]
        result_df = df_sorted[cols]

        # 1. HTML 표 생성 (줄바꿈 허용)
        table_body = ""
        for _, row in result_df.head(25).iterrows():
            table_body += f"""
            <tr>
                <td style="text-align:center;">{row['우선순위']}</td>
                <td style="text-align:center;">{row['판매처 유형']}</td>
                <td style="text-align:center;">{row['판매처/매장명']}</td>
                <td style="text-align:center;">{row['보유율']}</td>
                <td style="text-align:center;">{row['도서 가격 합계']}</td>
                <td style="text-align:left; line-height: 1.6;">{row['보유 도서 목록']}</td>
            </tr>
            """

        full_html = f"""
        <style>
            .custom-table {{
                width: 100%;
                border-collapse: collapse;
                font-size: 14px;
                color: #ffffff;
                background-color: #0e1117;
                margin-top: 10px;
            }}
            .custom-table th {{
                background-color: #262730;
                color: #ffffff;
                padding: 12px 10px;
                border: 1px solid #41444c;
                text-align: center;
                white-space: nowrap;
            }}
            .custom-table td {{
                padding: 10px 12px;
                border: 1px solid #31333f;
                vertical-align: middle;
            }}
            .custom-table tr:nth-child(even) {{
                background-color: #161922;
            }}
        </style>
        <table class="custom-table">
            <thead>
                <tr>
                    <th>우선순위</th>
                    <th>판매처 유형</th>
                    <th>판매처/매장명</th>
                    <th>보유율</th>
                    <th>도서 가격 합계</th>
                    <th>보유 도서 목록</th>
                </tr>
            </thead>
            <tbody>
                {table_body}
            </tbody>
        </table>
        """
        
        # st.markdown 대신 HTML 전용 랜더러 사용 (텍스트로 깨지는 현상 완벽 방지)
        st.html(full_html)
