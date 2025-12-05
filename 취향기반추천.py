"""
무신사 취향 기반 제품 추천 시스템
사용자의 취향을 분석하여 무신사에서 비슷한 제품을 추천합니다.
"""

from tavily import TavilyClient
from openai import OpenAI
import os
import json
from pathlib import Path

def extract_preference_keywords(user_input, openai_client):
    """
    GPT-4o를 사용하여 사용자 입력에서 취향 키워드를 추출합니다.
    """
    try:
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": """당신은 패션 쇼핑 어시스턴트입니다. 사용자의 취향을 분석하여 무신사에서 검색할 수 있는 키워드를 추출하세요.

다음 카테고리의 키워드를 추출해주세요:
1. 스타일: 미니멀, 미니멀리즘, 캠퍼스, 캠퍼스룩, 스트릿, 스트릿웨어, 오피스, 비즈니스, 캐주얼, 데이트, 댄디, 아메카지, 빈티지, 모던, 클래식, 시크, 페미닌, 유니섹스 등
2. 브랜드: 나이키, 아디다스, 컨버스, 반스, 뉴발란스, 아식스, 스투시, 커버낫, 디스이즈네버댓, 무신사, 무신사스탠다드 등
3. 편안함/감각: 편안한, 따뜻한, 시원한, 가벼운, 부드러운 등

응답은 JSON 형식으로, "keywords" 배열에 추출된 키워드만 포함하세요. 키워드가 없으면 빈 배열을 반환하세요.
예시: {"keywords": ["미니멀", "캠퍼스룩"]}"""
                },
                {
                    "role": "user",
                    "content": f"사용자 입력: {user_input}\n\n위 입력에서 패션 취향과 관련된 키워드를 추출해주세요. 반드시 JSON 형식으로 응답하세요."
                }
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        # JSON 응답 파싱
        result = json.loads(response.choices[0].message.content)
        keywords = result.get('keywords', [])
        
        # 키워드가 없으면 기본값 반환
        return keywords if keywords else ['무신사', '인기', '상품']
        
    except Exception as e:
        print(f"⚠️  GPT-4o 키워드 추출 오류: {e}")
        print("기본 키워드로 대체합니다.")
        # 오류 발생 시 기본 키워드 반환
        return ['무신사', '인기', '상품']

def search_products_with_tavily(keywords, tavily_client, natural_language_query=None):
    """
    Tavily를 사용하여 무신사 제품을 검색합니다.
    여러 쿼리로 나눠서 더 많은 결과를 수집합니다.
    """
    # 키워드 기반 쿼리
    keyword_query = ' '.join(keywords) if keywords else ''
    
    # 다양한 검색 쿼리 생성
    queries = []
    
    # 자연어 쿼리가 있으면 우선 사용
    if natural_language_query:
        queries.extend([
            f"{natural_language_query} 무신사 인기 상품",
            f"{natural_language_query} 무신사 상품",
            f"{natural_language_query} site:musinsa.com/products/",
            f"무신사 {natural_language_query}",
        ])
    
    # 키워드 기반 쿼리 추가
    if keyword_query:
        queries.extend([
            f"{keyword_query} 무신사 인기 상품",
            f"{keyword_query} 무신사 상품",
            f"{keyword_query} site:musinsa.com/products/",
            f"무신사 {keyword_query}",
        ])
    
    # 자연어와 키워드를 결합한 쿼리
    if natural_language_query and keyword_query:
        queries.append(f"{natural_language_query} {keyword_query} 무신사")
    
    # 쿼리가 없으면 기본 쿼리
    if not queries:
        queries = ["무신사 인기 상품"]
    
    all_results = []
    
    for query in queries:
        print(f"🔍 검색 중: {query}")
        try:
            # 더 많은 결과를 가져온 후 필터링
            response = tavily_client.search(
                query=query,
                search_depth="advanced",
                max_results=30,  # 필터링을 위해 더 많이 가져오기
                include_domains=["musinsa.com", "musinsa.co.kr", "www.musinsa.com"]
            )
            
            # www.musinsa.com/products/ 패턴만 필터링
            if response and 'results' in response:
                filtered_results = filter_product_pages(response['results'])
                all_results.extend(filtered_results)
                
        except Exception as e:
            print(f"⚠️  검색 오류 (계속 진행): {e}")
            # 도메인 제한 없이 재시도
            try:
                response = tavily_client.search(
                    query=query,
                    search_depth="advanced",
                    max_results=30
                )
                # 필터링 적용
                if response and 'results' in response:
                    filtered_results = filter_product_pages(response['results'])
                    all_results.extend(filtered_results)
            except Exception as e2:
                print(f"⚠️  재시도 실패 (계속 진행): {e2}")
                continue
    
    # 중복 제거 (URL 기준)
    seen_urls = set()
    unique_results = []
    for result in all_results:
        url = result.get('url', '')
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_results.append(result)
    
    # 결과 반환
    if unique_results:
        return {'results': unique_results[:15]}  # 최대 15개 반환
    else:
        return None

def filter_product_pages(results):
    """
    검색 결과에서 www.musinsa.com/products/ 패턴만 필터링합니다.
    """
    filtered = []
    
    for result in results:
        url = result.get('url', '')
        url_lower = url.lower()
        
        # www.musinsa.com/products/ 패턴만 허용
        if 'www.musinsa.com/products/' in url_lower or 'musinsa.com/products/' in url_lower:
            filtered.append(result)
    
    return filtered  # 모든 필터링된 결과 반환 (개수 제한은 상위 함수에서)

def calculate_relevance_score(product_info, user_keywords, openai_client):
    """
    GPT-4o를 사용하여 제품과 사용자 취향의 관련성 점수를 계산합니다.
    """
    try:
        title = product_info.get('title', '')
        content = product_info.get('content', '')
        product_text = f"{title} {content[:200]}"  # 제목 + 내용 일부
        
        response = openai_client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": """당신은 패션 추천 시스템입니다. 사용자의 취향 키워드와 제품 정보를 비교하여 관련성 점수를 0-100 사이로 매기고, 추천 이유를 작성하세요.

JSON 형식으로 응답해야 합니다:
{
  "score": 85,
  "reason": "미니멀 스타일과 캠퍼스룩에 적합한 제품입니다."
}"""
                },
                {
                    "role": "user",
                    "content": f"""사용자 취향 키워드: {', '.join(user_keywords)}

제품 정보:
제목: {title}
내용: {product_text}

위 제품이 사용자 취향과 얼마나 관련이 있는지 0-100 점수로 평가하고, 추천 이유를 한 문장으로 작성하세요. 반드시 JSON 형식으로 응답하세요."""
                }
            ],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        result = json.loads(response.choices[0].message.content)
        return result.get('score', 50), result.get('reason', '관련 제품입니다.')
        
    except Exception as e:
        print(f"⚠️  관련성 점수 계산 오류: {e}")
        # 기본 점수 계산 (키워드 매칭 기반)
        score = calculate_keyword_match_score(product_info, user_keywords)
        return score, "키워드 매칭 기반 추천"

def calculate_keyword_match_score(product_info, user_keywords):
    """
    키워드 매칭 기반 점수를 계산합니다 (fallback).
    """
    title = product_info.get('title', '').lower()
    content = product_info.get('content', '').lower()
    text = title + ' ' + content
    
    matches = 0
    for keyword in user_keywords:
        if keyword.lower() in text:
            matches += 1
    
    # 키워드 매칭 비율로 점수 계산 (0-100)
    if user_keywords:
        score = int((matches / len(user_keywords)) * 100)
    else:
        score = 50
    
    return score

def format_recommendations(response, user_keywords, openai_client):
    """
    Tavily 응답을 추천 제품 형식으로 포맷팅하고, 관련성 점수로 정렬합니다.
    """
    recommendations = []
    
    if not response or 'results' not in response:
        return recommendations
    
    print("\n📊 제품 관련성 점수 계산 중...")
    
    # 모든 제품에 대해 관련성 점수 계산
    scored_products = []
    for result in response['results']:
        title = result.get('title', '제목 없음')
        url = result.get('url', '')
        content = result.get('content', '')
        
        # 가격 정보 추출 시도
        price = None
        if '₩' in content or '원' in content:
            import re
            price_match = re.search(r'[₩\d,]+원?', content)
            if price_match:
                price = price_match.group()
        
        # 이미지 링크 추출 시도
        image_url = result.get('images', [])
        image = image_url[0] if image_url else None
        
        # 요약 생성 (내용의 처음 100자)
        summary = content[:100] + '...' if len(content) > 100 else content
        
        # 관련성 점수 계산
        relevance_score, reason = calculate_relevance_score(
            {'title': title, 'content': content},
            user_keywords,
            openai_client
        )
        
        scored_products.append({
            'title': title,
            'url': url,
            'price': price,
            'image': image,
            'summary': summary,
            'score': relevance_score,
            'reason': reason
        })
    
    # 점수 기준으로 정렬 (높은 순)
    scored_products.sort(key=lambda x: x['score'], reverse=True)
    
    # 상위 5개만 선택하고 순위 추가
    for idx, product in enumerate(scored_products[:5], 1):
        product['rank'] = idx
        recommendations.append(product)
    
    return recommendations

def display_recommendations(recommendations):
    """
    추천 제품을 보기 좋게 출력합니다. (추천 점수 포함)
    """
    if not recommendations:
        print("\n❌ 추천 제품을 찾을 수 없습니다.")
        return
    
    print("\n" + "="*60)
    print("✨ 취향 기반 추천 제품 (관련성 점수 순)")
    print("="*60)
    
    for rec in recommendations:
        print(f"\n[{rec['rank']}] {rec['title']}")
        print(f"   ⭐ 추천 점수: {rec['score']}/100")
        print(f"   💡 추천 이유: {rec['reason']}")
        if rec['price']:
            print(f"   💰 가격: {rec['price']}")
        if rec['image']:
            print(f"   🖼️  이미지: {rec['image']}")
        print(f"   📝 요약: {rec['summary']}")
        print(f"   🔗 링크: {rec['url']}")
        print("-" * 60)

def get_user_preferences_interactive():
    """
    사용자 친화적인 인터랙티브 방식으로 취향을 입력받습니다.
    """
    preferences = {
        'categories': [],
        'styles': [],
        'brands': [],
        'comfort': [],
        'price_range': None
    }
    
    print("\n" + "="*60)
    print("🎨 취향 선택하기")
    print("="*60)
    
    # 1. 카테고리 선택
    print("\n[1] 원하는 옷 카테고리를 선택하세요 (복수 선택 가능)")
    print("-" * 60)
    category_options = [
        ("1", "상의", "상의"),
        ("2", "하의", "하의"),
        ("3", "바지", "바지"),
        ("4", "아우터", "아우터"),
        ("5", "신발", "신발"),
        ("6", "악세서리", "악세서리"),
        ("7", "가방", "가방"),
        ("8", "모자", "모자"),
        ("0", "전체", None)
    ]
    
    for num, name, keyword in category_options:
        print(f"  {num}. {name}")
    
    category_input = input("\n선택 (번호를 쉼표로 구분, 예: 1,3,5 또는 0): ").strip()
    if category_input and category_input != "0":
        for num in category_input.split(','):
            num = num.strip()
            for opt_num, name, keyword in category_options:
                if opt_num == num and keyword:
                    preferences['categories'].append(keyword)
    
    # 2. 스타일 선택
    print("\n[2] 선호하는 스타일을 선택하세요 (복수 선택 가능)")
    print("-" * 60)
    style_options = [
        ("1", "미니멀", "미니멀리즘"),
        ("2", "캠퍼스룩", "캠퍼스"),
        ("3", "스트릿", "스트릿웨어"),
        ("4", "오피스", "비즈니스"),
        ("5", "캐주얼", "캐주얼"),
        ("6", "데이트", "데이트"),
        ("7", "댄디", "댄디"),
        ("8", "아메카지", "아메카지"),
        ("9", "빈티지", "빈티지"),
        ("10", "모던", "모던"),
        ("11", "클래식", "클래식"),
        ("12", "시크", "시크"),
        ("13", "페미닌", "페미닌"),
        ("14", "유니섹스", "유니섹스"),
        ("0", "건너뛰기", None)
    ]
    
    for num, name, keyword in style_options:
        print(f"  {num}. {name}")
    
    style_input = input("\n선택 (번호를 쉼표로 구분, 예: 1,3,5): ").strip()
    if style_input and style_input != "0":
        for num in style_input.split(','):
            num = num.strip()
            for opt_num, name, keyword in style_options:
                if opt_num == num and keyword:
                    preferences['styles'].append(keyword)
    
    # 3. 브랜드 입력 (선택사항)
    print("\n[3] 선호하는 브랜드가 있으면 입력하세요 (선택사항)")
    print("-" * 60)
    print("  예: 나이키, 아디다스, 컨버스")
    print("  브랜드가 없으면 Enter를 눌러 넘어가세요")
    
    brand_input = input("\n브랜드 입력 (쉼표로 구분 또는 Enter): ").strip()
    if brand_input:
        # 쉼표로 구분된 브랜드들을 리스트로 변환
        brands = [b.strip() for b in brand_input.split(',') if b.strip()]
        preferences['brands'].extend(brands)
    
    # 4. 편안함/감각 선택 (선택사항)
    print("\n[4] 원하는 느낌을 선택하세요 (선택사항, 복수 선택 가능)")
    print("-" * 60)
    comfort_options = [
        ("1", "편안한", "편안한"),
        ("2", "따뜻한", "따뜻한"),
        ("3", "시원한", "시원한"),
        ("4", "가벼운", "가벼운"),
        ("5", "부드러운", "부드러운"),
        ("0", "건너뛰기", None)
    ]
    
    for num, name, keyword in comfort_options:
        print(f"  {num}. {name}")
    
    comfort_input = input("\n선택 (번호를 쉼표로 구분, 예: 1,3 또는 0): ").strip()
    if comfort_input and comfort_input != "0":
        for num in comfort_input.split(','):
            num = num.strip()
            for opt_num, name, keyword in comfort_options:
                if opt_num == num and keyword:
                    preferences['comfort'].append(keyword)
    
    # 5. 가격대 선택 (선택사항)
    print("\n[5] 가격대를 선택하세요 (선택사항)")
    print("-" * 60)
    price_options = [
        ("1", "5만원 이하", "저렴"),
        ("2", "5만원 ~ 10만원", "보통"),
        ("3", "10만원 ~ 20만원", "중간"),
        ("4", "20만원 이상", "프리미엄"),
        ("0", "가격 무관", None)
    ]
    
    for num, name, keyword in price_options:
        print(f"  {num}. {name}")
    
    price_input = input("\n선택 (번호 하나만, 예: 2 또는 0): ").strip()
    if price_input and price_input != "0":
        for opt_num, name, keyword in price_options:
            if opt_num == price_input and keyword:
                preferences['price_range'] = keyword
    
    # 선택한 취향 요약
    print("\n" + "="*60)
    print("📋 선택한 취향 요약")
    print("="*60)
    if preferences['categories']:
        print(f"  카테고리: {', '.join(preferences['categories'])}")
    if preferences['styles']:
        print(f"  스타일: {', '.join(preferences['styles'])}")
    if preferences['brands']:
        print(f"  브랜드: {', '.join(preferences['brands'])}")
    if preferences['comfort']:
        print(f"  느낌: {', '.join(preferences['comfort'])}")
    if preferences['price_range']:
        print(f"  가격대: {preferences['price_range']}")
    
    # 키워드 리스트 생성
    all_keywords = []
    all_keywords.extend(preferences['categories'])
    all_keywords.extend(preferences['styles'])
    all_keywords.extend(preferences['brands'])
    all_keywords.extend(preferences['comfort'])
    if preferences['price_range']:
        all_keywords.append(preferences['price_range'])
    
    return all_keywords if all_keywords else ['무신사', '인기', '상품']

def load_api_key_from_env(key_name):
    """
    Hackathon 폴더 바로 아래에 있는 .env 파일에서 API 키를 읽습니다.
    key_name: 'TAVILY_API_KEY' 또는 'OPENAI_API_KEY'
    """
    # 현재 파일의 경로에서 Hackathon 폴더 경로 찾기
    current_file = Path(__file__).resolve()
    hackathon_dir = current_file.parent.parent  # rmdnps10 -> Hackathon
    
    # 환경 변수 먼저 확인
    api_key = os.getenv(key_name)
    if api_key:
        return api_key.strip()
    
    # Hackathon 폴더에서 .env 파일 찾기
    env_file = hackathon_dir / '.env'
    if env_file.exists():
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # 주석이나 빈 줄 건너뛰기
                    if not line or line.startswith('#'):
                        continue
                    # KEY=value 형식 파싱
                    if key_name in line:
                        if '=' in line:
                            key, value = line.split('=', 1)
                            if key.strip() == key_name:
                                api_key = value.strip().strip('"').strip("'")
                                if api_key:
                                    return api_key
        except Exception as e:
            print(f"⚠️  .env 파일 읽기 오류: {e}")
    
    return None

def main():
    """
    메인 함수: 터미널에서 사용자 입력을 받아 추천을 제공합니다.
    """
    # Tavily API 키 확인
    tavily_api_key = load_api_key_from_env('TAVILY_API_KEY')
    if not tavily_api_key:
        print("⚠️  TAVILY_API_KEY를 찾을 수 없습니다.")
        print("Hackathon 폴더 바로 아래에 .env 파일을 생성하고 다음 형식으로 입력하세요:")
        print("  TAVILY_API_KEY=your-api-key")
        tavily_api_key = input("\n또는 여기에 Tavily API 키를 직접 입력하세요: ").strip()
        if not tavily_api_key:
            print("❌ Tavily API 키가 필요합니다.")
            return
    
    # OpenAI API 키 확인
    openai_api_key = load_api_key_from_env('OPENAI_API_KEY')
    if not openai_api_key:
        print("⚠️  OPENAI_API_KEY를 찾을 수 없습니다.")
        print("Hackathon 폴더 바로 아래에 .env 파일을 생성하고 다음 형식으로 입력하세요:")
        print("  OPENAI_API_KEY=your-api-key")
        openai_api_key = input("\n또는 여기에 OpenAI API 키를 직접 입력하세요: ").strip()
        if not openai_api_key:
            print("❌ OpenAI API 키가 필요합니다.")
            return
    
    # 클라이언트 초기화
    tavily_client = TavilyClient(api_key=tavily_api_key)
    openai_client = OpenAI(api_key=openai_api_key)
    
    print("="*60)
    print("🛍️  무신사 취향 기반 제품 추천 시스템")
    print("="*60)
    print("\n💡 사용 방법:")
    print("  - 메뉴에서 취향을 선택하시면 됩니다.")
    print("  - 각 단계에서 원하는 항목의 번호를 입력하세요.")
    print("  - 복수 선택 시 쉼표로 구분하세요 (예: 1,3,5)")
    print("\n종료하려면 'quit' 또는 'exit'를 입력하세요.")
    print("="*60)
    
    while True:
        try:
            # 사용자 취향 선택 (인터랙티브)
            keywords = get_user_preferences_interactive()
            
            if not keywords or keywords == ['무신사', '인기', '상품']:
                print("\n⚠️  취향을 선택하지 않았습니다. 기본 추천을 진행합니다.")
            
            print(f"\n📌 선택된 키워드: {', '.join(keywords)}")
            
            # 추가 설명 입력 (선택사항) - 자연어로 그대로 사용
            natural_language_query = input("\n💬 추가로 원하는 스타일이나 설명이 있으면 자연어로 입력하세요 (없으면 Enter): ").strip()
            
            if natural_language_query:
                print(f"\n📝 자연어 검색어: {natural_language_query}")
            
            # 제품 검색 (키워드 + 자연어)
            response = search_products_with_tavily(keywords, tavily_client, natural_language_query)
            
            # 추천 제품 포맷팅 (관련성 점수 계산 및 정렬)
            recommendations = format_recommendations(response, keywords, openai_client)
            
            # 결과 출력
            display_recommendations(recommendations)
            
            # 다시 검색할지 물어보기
            print("\n" + "="*60)
            continue_search = input("다시 검색하시겠습니까? (y/n 또는 quit): ").strip().lower()
            
            if continue_search in ['n', 'no', '아니오', 'quit', 'exit', '종료', 'q']:
                print("\n👋 이용해주셔서 감사합니다!")
                break
            
        except KeyboardInterrupt:
            print("\n\n👋 이용해주셔서 감사합니다!")
            break
        except Exception as e:
            print(f"\n❌ 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            
            # 오류 후에도 계속할지 물어보기
            continue_after_error = input("\n계속하시겠습니까? (y/n): ").strip().lower()
            if continue_after_error in ['n', 'no', '아니오']:
                print("\n👋 이용해주셔서 감사합니다!")
                break

if __name__ == "__main__":
    main()

