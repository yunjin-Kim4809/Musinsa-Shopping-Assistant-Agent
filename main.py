"""
무신사 쇼핑 도움 에이전트 - 통합 메인 프로그램
사용자가 원하는 기능을 선택하여 실행할 수 있습니다.
"""

import os
import sys

# 프로젝트 루트의 .env 파일을 환경변수로 로드 (python-dotenv 사용 시)
def _load_dotenv():
    project_dir = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(project_dir, ".env")
    try:
        from dotenv import load_dotenv
        load_dotenv(env_path)
    except ImportError:
        # python-dotenv 없을 때 .env 파일 직접 읽기
        if os.path.isfile(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, _, value = line.partition("=")
                        key, value = key.strip(), value.strip().strip("'\"")
                        if key in ("TAVILY_API_KEY", "OPENAI_API_KEY") and value and not os.getenv(key):
                            os.environ[key] = value
            except Exception:
                pass
_load_dotenv()

from price_rating_comparison import PriceRatingComparisonAgent
from preference_based_recommendation import PreferenceBasedRecommendationAgent
from review_summary_agent import ReviewSummaryAgent

# 취향기반추천.py 함수들 import
try:
    from 취향기반추천 import (
        get_user_preferences_interactive,
        search_products_with_tavily,
        format_recommendations,
        display_recommendations,
        load_api_key_from_env
    )
    from tavily import TavilyClient
    from openai import OpenAI
    TASTE_RECOMMENDATION_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ 취향기반추천 모듈을 불러올 수 없습니다: {e}")
    TASTE_RECOMMENDATION_AVAILABLE = False


def print_menu():
    """메뉴를 출력합니다."""
    print("\n" + "="*60)
    print("🛍️  무신사 쇼핑 도움 에이전트")
    print("="*60)
    print("1. 제품 가격 및 평점 비교 분석")
    print("2. 사용자 취향 기반 제품 추천")
    print("3. 제품 리뷰 기반 장단점 요약")
    if TASTE_RECOMMENDATION_AVAILABLE:
        print("4. 취향 기반 제품 추천 (인터랙티브)")
        print("5. 종료")
    else:
        print("4. 종료")
    print("="*60)


def get_user_choice() -> int:
    """사용자로부터 메뉴 선택을 받습니다."""
    max_choice = 5 if TASTE_RECOMMENDATION_AVAILABLE else 4
    while True:
        try:
            choice = input(f"\n원하는 기능을 선택하세요 (1-{max_choice}): ").strip()
            choice_num = int(choice)
            if 1 <= choice_num <= max_choice:
                return choice_num
            else:
                print(f"⚠️ 1부터 {max_choice} 사이의 숫자를 입력해주세요.")
        except ValueError:
            print("⚠️ 숫자를 입력해주세요.")
        except KeyboardInterrupt:
            print("\n\n프로그램을 종료합니다.")
            sys.exit(0)


def check_api_key() -> str:
    """환경변수 또는 .env에서 TAVILY_API_KEY를 확인하고 반환합니다."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key and TASTE_RECOMMENDATION_AVAILABLE:
        api_key = load_api_key_from_env("TAVILY_API_KEY")
    if not api_key:
        print("⚠️ 환경변수 TAVILY_API_KEY가 설정되지 않았습니다.")
        print("환경변수를 설정하거나 직접 API 키를 입력해주세요.")
        print("  → 프로젝트 폴더에 .env 파일을 만들고 TAVILY_API_KEY=키값 을 넣어도 됩니다.")
        api_key = input("TAVILY_API_KEY를 입력하세요 (또는 Enter로 종료): ").strip()
        if not api_key:
            print("프로그램을 종료합니다.")
            sys.exit(0)
    return api_key


def check_openai_api_key() -> str:
    """환경변수 또는 .env에서 OPENAI_API_KEY를 확인하고 반환합니다."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        # load_api_key_from_env 함수 사용 시도
        if TASTE_RECOMMENDATION_AVAILABLE:
            api_key = load_api_key_from_env("OPENAI_API_KEY")
        if not api_key:
            print("⚠️ 환경변수 OPENAI_API_KEY가 설정되지 않았습니다.")
            print("환경변수를 설정하거나 직접 API 키를 입력해주세요.")
            print("  → 프로젝트 폴더에 .env 파일을 만들고 OPENAI_API_KEY=키값 을 넣어도 됩니다.")
            api_key = input("OPENAI_API_KEY를 입력하세요 (또는 Enter로 종료): ").strip()
            if not api_key:
                print("프로그램을 종료합니다.")
                sys.exit(0)
    return api_key


def run_price_comparison(api_key: str):
    """제품 가격 및 평점 비교 분석을 실행합니다."""
    print("\n" + "-"*60)
    print("📊 제품 가격 및 평점 비교 분석")
    print("-"*60)
    print("\n비교할 제품 2개 이상을 입력해주세요.")
    print("예: '나이키 에어 포스 1 07 W - 화이트와 푸마 터프패디드 FS 코듀로이'")
    print("또는: 'A 코트 vs B 코트'")
    
    product_query = input("\n제품 입력: ").strip()
    
    if not product_query:
        print("⚠️ 제품명을 입력해주세요.")
        return
    
    try:
        agent = PriceRatingComparisonAgent(api_key=api_key)
        print(f"\n📊 제품 비교 분석 시작: {product_query}\n")
        result = agent.compare_products(product_query)
        print("\n" + "="*60)
        print(result)
        print("="*60)
    except Exception as e:
        print(f"❌ 오류가 발생했습니다: {e}")


def run_preference_recommendation(api_key: str):
    """사용자 취향 기반 제품 추천을 실행합니다."""
    print("\n" + "-"*60)
    print("🎯 사용자 취향 기반 제품 추천")
    print("-"*60)
    print("\n취향 키워드를 입력해주세요.")
    print("예: '미니멀리즘, 30만원대, 아르켓 느낌'")
    print("또는: '스트릿 스타일, 20만원, 나이키'")
    print("\n입력 가능한 키워드:")
    print("  - 스타일: 미니멀, 스트릿, 캠퍼스, 오피스, 빈티지, 러블리")
    print("  - 예산: 숫자 + '만원대' 또는 '만원' (예: 30만원대, 50만원)")
    print("  - 브랜드: 나이키, 아디다스, 아르켓, 아크네 등")
    
    preference_input = input("\n취향 입력: ").strip()
    
    if not preference_input:
        print("⚠️ 취향 키워드를 입력해주세요.")
        return
    
    try:
        agent = PreferenceBasedRecommendationAgent(tavily_api_key=api_key)
        print(f"\n📊 제품 추천 시작: {preference_input}\n")
        result = agent.recommend_products(preference_input)
        print("\n" + "="*60)
        print(result)
        print("="*60)
    except Exception as e:
        print(f"❌ 오류가 발생했습니다: {e}")


def run_review_summary(api_key: str):
    """제품 리뷰 기반 장단점 요약을 실행합니다."""
    print("\n" + "-"*60)
    print("📝 제품 리뷰 기반 장단점 요약")
    print("-"*60)
    print("\n분석할 제품명을 입력해주세요.")
    print("예: '나이키 에어맥스'")
    print("또는: '무신사 코트'")
    
    product_name = input("\n제품명 입력: ").strip()
    
    if not product_name:
        print("⚠️ 제품명을 입력해주세요.")
        return
    
    try:
        agent = ReviewSummaryAgent(tavily_api_key=api_key)
        print(f"\n📊 제품 리뷰 분석 시작: {product_name}\n")
        result = agent.summarize_reviews(product_name)
        print("\n" + "="*60)
        print(result)
        print("="*60)
    except Exception as e:
        print(f"❌ 오류가 발생했습니다: {e}")


def run_taste_recommendation(tavily_api_key: str, openai_api_key: str):
    """취향 기반 제품 추천 (인터랙티브)을 실행합니다."""
    if not TASTE_RECOMMENDATION_AVAILABLE:
        print("❌ 취향 기반 추천 기능을 사용할 수 없습니다.")
        return
    
    print("\n" + "-"*60)
    print("🎨 취향 기반 제품 추천 (인터랙티브)")
    print("-"*60)
    print("\n💡 사용 방법:")
    print("  - 메뉴에서 취향을 선택하시면 됩니다.")
    print("  - 각 단계에서 원하는 항목의 번호를 입력하세요.")
    print("  - 복수 선택 시 쉼표로 구분하세요 (예: 1,3,5)")
    print("-"*60)
    
    try:
        # 클라이언트 초기화
        tavily_client = TavilyClient(api_key=tavily_api_key)
        openai_client = OpenAI(api_key=openai_api_key)
        
        # 사용자 취향 선택 (인터랙티브)
        keywords = get_user_preferences_interactive()
        
        if not keywords or keywords == ['무신사', '인기', '상품']:
            print("\n⚠️  취향을 선택하지 않았습니다. 기본 추천을 진행합니다.")
        
        print(f"\n📌 선택된 키워드: {', '.join(keywords)}")
        
        # 추가 설명 입력 (선택사항)
        natural_language_query = input("\n💬 추가로 원하는 스타일이나 설명이 있으면 자연어로 입력하세요 (없으면 Enter): ").strip()
        
        if natural_language_query:
            print(f"\n📝 자연어 검색어: {natural_language_query}")
        
        # 제품 검색 (키워드 + 자연어)
        response = search_products_with_tavily(keywords, tavily_client, natural_language_query)

        if not response or not response.get("results"):
            print("\n⚠️ 검색 결과가 없습니다. 다른 키워드나 스타일로 다시 시도해 보세요.")
            return

        # 추천 제품 포맷팅 (관련성 점수 계산 및 정렬)
        recommendations = format_recommendations(response, keywords, openai_client)
        
        # 결과 출력
        display_recommendations(recommendations)
        
    except Exception as e:
        print(f"❌ 오류가 발생했습니다: {e}")
        import traceback
        traceback.print_exc()


def main():
    """메인 함수"""
    # API 키 확인
    api_key = check_api_key()
    
    while True:
        try:
            # 메뉴 출력
            print_menu()
            
            # 사용자 선택 받기
            choice = get_user_choice()
            
            # 선택에 따라 기능 실행
            if choice == 1:
                run_price_comparison(api_key)
            elif choice == 2:
                run_preference_recommendation(api_key)
            elif choice == 3:
                run_review_summary(api_key)
            elif choice == 4:
                if TASTE_RECOMMENDATION_AVAILABLE:
                    # OpenAI API 키 확인
                    openai_api_key = check_openai_api_key()
                    run_taste_recommendation(api_key, openai_api_key)
                else:
                    print("\n👋 프로그램을 종료합니다. 감사합니다!")
                    break
            elif choice == 5:
                print("\n👋 프로그램을 종료합니다. 감사합니다!")
                break
            
            # 다음 작업 여부 확인
            exit_choice = 5 if TASTE_RECOMMENDATION_AVAILABLE else 4
            if choice != exit_choice:
                continue_choice = input("\n다른 기능을 사용하시겠습니까? (y/n): ").strip().lower()
                if continue_choice not in ['y', 'yes', '예', 'ㅇ']:
                    print("\n👋 프로그램을 종료합니다. 감사합니다!")
                    break
                    
        except KeyboardInterrupt:
            print("\n\n👋 프로그램을 종료합니다. 감사합니다!")
            break
        except Exception as e:
            print(f"\n❌ 예상치 못한 오류가 발생했습니다: {e}")
            print("프로그램을 계속 진행합니다...\n")


if __name__ == "__main__":
    main()

