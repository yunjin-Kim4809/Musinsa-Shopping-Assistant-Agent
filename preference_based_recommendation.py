"""
무신사 쇼핑 도움 에이전트 - 사용자 취향 기반 제품 추천
Tavily API를 사용하여 사용자의 취향 키워드에 맞는 무신사 제품을 우선적으로 검색하고 추천합니다.
"""

import os
import re
from typing import List, Dict, Optional, Tuple
from tavily import TavilyClient
import json


class PreferenceBasedRecommendationAgent:
    """사용자 취향 기반 제품 추천을 수행하는 에이전트"""
    
    # 스타일 키워드 사전
    STYLE_KEYWORDS = {
        "미니멀": ["미니멀", "미니멀리즘", "심플", "깔끔", "모노톤"],
        "스트릿": ["스트릿", "캐주얼", "힙", "유니크"],
        "캠퍼스": ["캠퍼스", "학생", "편안", "컴포트"],
        "오피스": ["오피스", "비즈니스", "정장", "포멀"],
        "빈티지": ["빈티지", "레트로", "옛날"],
        "러블리": ["러블리", "큐트", "여성스러운"]
    }
    
    def __init__(self, tavily_api_key: Optional[str] = None, openai_api_key: Optional[str] = None):
        """
        Args:
            tavily_api_key: Tavily API 키. 없으면 환경변수 TAVILY_API_KEY에서 로드
            openai_api_key: OpenAI API 키 (선택적, 추천 이유 생성 시 사용)
        """
        self.tavily_api_key = tavily_api_key or os.getenv("TAVILY_API_KEY")
        if not self.tavily_api_key:
            raise ValueError("Tavily API 키가 필요합니다. 환경변수 TAVILY_API_KEY를 설정하거나 tavily_api_key 파라미터를 제공하세요.")
        
        self.openai_api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        
        self.tavily_client = TavilyClient(api_key=self.tavily_api_key)
        
        # OpenAI 클라이언트 초기화 (선택적)
        if self.openai_api_key:
            try:
                from openai import OpenAI
                self.openai_client = OpenAI(api_key=self.openai_api_key)
                self.use_openai = True
            except ImportError:
                self.openai_client = None
                self.use_openai = False
        else:
            self.openai_client = None
            self.use_openai = False
    
    def parse_preference_keywords(self, preference_input: str) -> Dict:
        """
        사용자 취향 키워드를 파싱하여 구조화된 정보로 변환합니다.
        
        Args:
            preference_input: 취향 키워드 문자열 (예: "미니멀리즘", "30만원대", "아르켓 느낌")
            
        Returns:
            파싱된 취향 정보 딕셔너리
        """
        preferences = {
            "style": [],
            "budget": None,
            "budget_min": None,
            "budget_max": None,
            "brand": [],
            "keywords": []
        }
        
        # 스타일 키워드 추출
        input_lower = preference_input.lower()
        for style_name, keywords in self.STYLE_KEYWORDS.items():
            if any(keyword in preference_input or keyword in input_lower for keyword in keywords):
                preferences["style"].append(style_name)
        
        # 예산 추출
        budget_patterns = [
            r'(\d+)만원대',
            r'(\d+)만\s*원대',
            r'(\d+)\s*만원',
            r'(\d+)\s*만\s*원',
            r'예산\s*[:]\s*(\d+)\s*만원',
            r'(\d+)\s*~?\s*(\d+)\s*만원'
        ]
        
        for pattern in budget_patterns:
            matches = re.findall(pattern, preference_input)
            if matches:
                if isinstance(matches[0], tuple):
                    # 범위 예산 (예: "20~30만원")
                    min_budget = int(matches[0][0])
                    max_budget = int(matches[0][1]) if len(matches[0]) > 1 else min_budget + 10
                    preferences["budget_min"] = min_budget * 10000
                    preferences["budget_max"] = max_budget * 10000
                    preferences["budget"] = f"{min_budget}~{max_budget}만원"
                else:
                    # 단일 예산 (예: "30만원대")
                    budget = int(matches[0])
                    preferences["budget"] = f"{budget}만원대"
                    preferences["budget_min"] = budget * 10000
                    preferences["budget_max"] = (budget + 9) * 10000
        
        # 브랜드 키워드 추출
        brand_keywords = [
            "아르켓", "아크네", "나이키", "아디다스", "무신사", "쿠론", "스톤아일랜드",
            "커버낫", "디스이즈네버댓", "노스페이스", "패트아그", "아더에러"
        ]
        
        for brand in brand_keywords:
            if brand in preference_input or brand.lower() in input_lower:
                preferences["brand"].append(brand)
        
        # 기타 키워드 추출
        keywords = preference_input.split(",")
        for keyword in keywords:
            keyword = keyword.strip()
            if keyword and len(keyword) > 1:
                preferences["keywords"].append(keyword)
        
        return preferences
    
    def search_similar_products(self, preferences: Dict) -> List[Dict]:
        """
        사용자 취향에 맞는 유사 제품을 검색합니다.
        무신사 제품을 우선적으로 검색합니다.
        
        Args:
            preferences: 파싱된 취향 정보 딕셔너리
            
        Returns:
            검색된 제품 정보 리스트
        """
        # 무신사 우선 검색 쿼리 생성
        musinsa_queries = []
        
        # 스타일 기반 무신사 쿼리
        if preferences["style"]:
            for style in preferences["style"]:
                musinsa_queries.append(f"{style} 스타일 무신사 인기 제품")
                musinsa_queries.append(f"{style} 무신사 추천 제품")
                musinsa_queries.append(f"{style} 무신사 제품")
                musinsa_queries.append(f"{style} site:musinsa.com")
        
        # 브랜드 기반 무신사 쿼리
        if preferences["brand"]:
            for brand in preferences["brand"]:
                musinsa_queries.append(f"{brand} 무신사 가성비 제품")
                musinsa_queries.append(f"{brand} 무신사 비슷한 제품")
                musinsa_queries.append(f"{brand} 무신사 추천")
        
        # 키워드 기반 무신사 쿼리
        if preferences["keywords"]:
            for keyword in preferences["keywords"][:3]:  # 최대 3개
                musinsa_queries.append(f"{keyword} 무신사 제품")
                musinsa_queries.append(f"{keyword} site:musinsa.com")
        
        # 예산 기반 무신사 쿼리
        if preferences["budget"]:
            musinsa_queries.append(f"{preferences['budget']} 무신사 추천 제품")
            musinsa_queries.append(f"{preferences['budget']} 무신사 인기 제품")
        
        # 기본 무신사 쿼리
        if not musinsa_queries:
            musinsa_queries.append("무신사 인기 제품")
            musinsa_queries.append("site:musinsa.com 인기")
        
        # 일반 검색 쿼리 (무신사 제품이 부족할 경우)
        general_queries = []
        if preferences["style"]:
            for style in preferences["style"]:
                general_queries.append(f"{style} 스타일 인기 제품")
        
        musinsa_products = []
        general_products = []
        
        # 먼저 무신사 제품 검색
        for query in musinsa_queries[:8]:  # 최대 8개 쿼리
            try:
                response = self.tavily_client.search(
                    query=query,
                    search_depth="advanced",
                    max_results=5
                )
                
                if response and "results" in response:
                    for result in response["results"]:
                        product_info = self._extract_product_info(result, preferences)
                        if product_info:
                            url = result.get("url", "").lower()
                            content = result.get("content", "").lower()
                            name = product_info.get("name", "").lower()
                            
                            # 무신사 관련 제품 우선 분류
                            if ("musinsa" in url or "무신사" in content or 
                                "musinsa" in content or "무신사" in name):
                                musinsa_products.append(product_info)
                            else:
                                general_products.append(product_info)
            except Exception as e:
                print(f"검색 중 오류 발생 ({query}): {e}")
                continue
        
        # 무신사 제품이 충분하지 않으면 일반 검색 추가
        if len(musinsa_products) < 3:
            for query in general_queries[:3]:  # 최대 3개 쿼리
                try:
                    response = self.tavily_client.search(
                        query=query,
                        search_depth="advanced",
                        max_results=3
                    )
                    
                    if response and "results" in response:
                        for result in response["results"]:
                            product_info = self._extract_product_info(result, preferences)
                            if product_info:
                                url = result.get("url", "").lower()
                                content = result.get("content", "").lower()
                                
                                # 무신사 관련이 아닌 것만 추가
                                if ("musinsa" not in url and "무신사" not in content and 
                                    "musinsa" not in content):
                                    general_products.append(product_info)
                except Exception as e:
                    print(f"검색 중 오류 발생 ({query}): {e}")
                    continue
        
        # 중복 제거 (무신사 제품 우선)
        unique_products = []
        seen_names = set()
        
        # 먼저 무신사 제품 추가
        for product in musinsa_products:
            name = product.get("name", "")
            if name and name not in seen_names:
                seen_names.add(name)
                unique_products.append(product)
        
        # 그 다음 일반 제품 추가
        for product in general_products:
            name = product.get("name", "")
            if name and name not in seen_names:
                seen_names.add(name)
                unique_products.append(product)
        
        return unique_products
    
    def _extract_product_info(self, search_result: Dict, preferences: Dict) -> Optional[Dict]:
        """
        검색 결과에서 제품 정보를 추출합니다.
        
        Args:
            search_result: Tavily 검색 결과
            preferences: 사용자 취향 정보
            
        Returns:
            추출된 제품 정보 딕셔너리
        """
        content = search_result.get("content", "")
        title = search_result.get("title", "")
        url = search_result.get("url", "")
        
        if not content and not title:
            return None
        
        # 제품명 추출
        product_name = title
        if not product_name or len(product_name) > 100:
            # 내용에서 제품명 추출 시도
            lines = content.split("\n")
            for line in lines[:5]:
                if len(line) > 10 and len(line) < 80:
                    product_name = line.strip()
                    break
        
        if not product_name:
            return None
        
        # 가격 추출
        price_info = self._extract_price(content + " " + title)
        
        # 이미지 링크 추출 (URL에서)
        image_url = None
        if url:
            # Tavily 결과에 이미지 정보가 있을 수 있음
            image_url = search_result.get("raw_image_url") or url
        
        product_info = {
            "name": product_name[:100],  # 제품명 최대 100자
            "price": price_info.get("price"),
            "original_price": price_info.get("original_price"),
            "discount_rate": price_info.get("discount_rate"),
            "image_url": image_url,
            "url": url,
            "content": content[:500],  # 내용 요약
            "relevance_score": self._calculate_relevance_score(product_name, content, preferences)
        }
        
        return product_info
    
    def _extract_price(self, text: str) -> Dict:
        """텍스트에서 가격 정보를 추출합니다."""
        price_info = {
            "price": None,
            "original_price": None,
            "discount_rate": None
        }
        
        # 가격 패턴
        price_patterns = [
            r'(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*원',
            r'₩\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)',
        ]
        
        prices = []
        for pattern in price_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                try:
                    price = int(match.replace(",", "").replace(".", ""))
                    if 10000 <= price <= 10000000:  # 합리적인 가격 범위
                        prices.append(price)
                except:
                    continue
        
        if prices:
            price_info["price"] = min(prices)
        
        # 할인율 추출
        discount_patterns = [
            r'(\d+)%\s*할인',
            r'(\d+)%\s*OFF',
        ]
        
        for pattern in discount_patterns:
            matches = re.findall(pattern, text)
            if matches:
                try:
                    price_info["discount_rate"] = int(matches[0])
                except:
                    continue
        
        return price_info
    
    def _calculate_relevance_score(self, product_name: str, content: str, preferences: Dict) -> float:
        """제품이 사용자 취향에 얼마나 맞는지 점수를 계산합니다. 무신사 제품에 가산점을 부여합니다."""
        score = 0.0
        combined_text = (product_name + " " + content).lower()
        
        # 무신사 제품 가산점 (우선순위)
        if "musinsa" in combined_text or "무신사" in combined_text:
            score += 25  # 무신사 제품은 높은 가산점
        
        # 스타일 매칭 점수
        style_score = 0
        for style in preferences.get("style", []):
            for keyword in self.STYLE_KEYWORDS.get(style, []):
                if keyword in combined_text:
                    style_score += 2
        
        score += min(style_score, 10)  # 최대 10점
        
        # 브랜드 매칭 점수
        brand_score = 0
        for brand in preferences.get("brand", []):
            if brand.lower() in combined_text:
                brand_score += 5
        
        score += min(brand_score, 15)  # 최대 15점
        
        # 예산 매칭 점수
        price = self._extract_price(combined_text).get("price")
        if price and preferences.get("budget_min") and preferences.get("budget_max"):
            if preferences["budget_min"] <= price <= preferences["budget_max"]:
                score += 20  # 예산 범위 내
            elif preferences["budget_min"] * 0.8 <= price <= preferences["budget_max"] * 1.2:
                score += 10  # 예산 범위 근처
        
        # 키워드 매칭 점수
        keyword_score = 0
        for keyword in preferences.get("keywords", []):
            if keyword.lower() in combined_text:
                keyword_score += 3
        
        score += min(keyword_score, 10)  # 최대 10점
        
        return score
    
    def select_top_products(self, products: List[Dict], preferences: Dict, top_n: int = 3) -> List[Dict]:
        """
        검색된 제품 중에서 사용자 취향에 가장 맞는 상위 N개를 선정합니다.
        
        Args:
            products: 검색된 제품 리스트
            preferences: 사용자 취향 정보
            top_n: 선정할 제품 개수
            
        Returns:
            선정된 제품 리스트
        """
        # 관련도 점수로 정렬
        sorted_products = sorted(products, key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        # 예산 필터링
        if preferences.get("budget_min") and preferences.get("budget_max"):
            filtered_products = []
            for product in sorted_products:
                price = product.get("price")
                if price:
                    # 예산 범위 내이거나 근처인 제품만 포함
                    if preferences["budget_min"] * 0.7 <= price <= preferences["budget_max"] * 1.3:
                        filtered_products.append(product)
                else:
                    # 가격 정보가 없으면 일단 포함
                    filtered_products.append(product)
            
            if filtered_products:
                sorted_products = filtered_products
        
        return sorted_products[:top_n]
    
    def generate_recommendation_reason(self, product: Dict, preferences: Dict) -> str:
        """
        제품 추천 이유를 생성합니다.
        
        Args:
            product: 제품 정보 딕셔너리
            preferences: 사용자 취향 정보
            
        Returns:
            추천 이유 문자열
        """
        reasons = []
        
        # 스타일 매칭 이유
        product_text = (product.get("name", "") + " " + product.get("content", "")).lower()
        matched_styles = []
        for style in preferences.get("style", []):
            for keyword in self.STYLE_KEYWORDS.get(style, []):
                if keyword in product_text:
                    matched_styles.append(style)
                    break
        
        if matched_styles:
            reasons.append(f"{', '.join(set(matched_styles))} 스타일과 일치합니다")
        
        # 브랜드 매칭 이유
        matched_brands = []
        for brand in preferences.get("brand", []):
            if brand.lower() in product_text:
                matched_brands.append(brand)
        
        if matched_brands:
            reasons.append(f"{', '.join(matched_brands)} 브랜드의 느낌과 유사합니다")
        
        # 예산 매칭 이유
        price = product.get("price")
        if price and preferences.get("budget"):
            reasons.append(f"예산({preferences['budget']})에 부합합니다")
        
        # 가성비 이유
        if price and preferences.get("budget_max"):
            if price < preferences["budget_max"] * 0.8:
                reasons.append("가격 대비 가성비가 우수합니다")
        
        # 할인 정보
        if product.get("discount_rate"):
            reasons.append(f"{product['discount_rate']}% 할인 중입니다")
        
        # 기본 추천 이유
        if not reasons:
            reasons.append("사용자 취향 키워드와 관련된 인기 제품입니다")
        
        return " | ".join(reasons)
    
    def recommend_products(self, preference_input: str) -> str:
        """
        사용자 취향에 맞는 제품을 추천하고 마크다운 형식으로 반환합니다.
        
        Args:
            preference_input: 취향 키워드 문자열 (예: "미니멀리즘", "30만원대", "아르켓 느낌")
            
        Returns:
            마크다운 형식의 추천 결과
        """
        print(f"🔍 취향 키워드 파싱: {preference_input}")
        
        # 취향 키워드 파싱
        preferences = self.parse_preference_keywords(preference_input)
        
        print(f"  → 스타일: {preferences['style']}")
        print(f"  → 예산: {preferences['budget']}")
        print(f"  → 브랜드: {preferences['brand']}")
        
        print(f"🔎 유사 제품 검색 중...")
        
        # 유사 제품 검색
        products = self.search_similar_products(preferences)
        
        if not products:
            return f"⚠️ '{preference_input}'에 맞는 제품을 찾을 수 없습니다."
        
        print(f"  → {len(products)}개의 제품 검색 완료")
        print(f"📊 상위 3개 제품 선정 중...")
        
        # 상위 3개 제품 선정
        top_products = self.select_top_products(products, preferences, top_n=3)
        
        # 마크다운 형식으로 변환
        return self._generate_markdown_recommendation(preference_input, top_products, preferences)
    
    def _generate_markdown_recommendation(self, preference_input: str, products: List[Dict], preferences: Dict) -> str:
        """
        추천 결과를 마크다운 형식으로 생성합니다.
        
        Args:
            preference_input: 원본 취향 키워드 입력
            products: 추천 제품 리스트
            preferences: 파싱된 취향 정보
            
        Returns:
            마크다운 형식의 추천 결과
        """
        # 취향 요약
        preference_summary = []
        if preferences.get("style"):
            preference_summary.extend(preferences["style"])
        if preferences.get("budget"):
            preference_summary.append(preferences["budget"])
        if preferences.get("brand"):
            preference_summary.extend(preferences["brand"])
        
        preference_text = ", ".join(preference_summary) if preference_summary else preference_input
        
        markdown = f"### ✨ [{preference_text}] 기반 맞춤 추천 제품 3가지\n\n"
        
        for idx, product in enumerate(products, 1):
            name = product.get("name", "제품명 없음")
            price = product.get("price")
            
            # 가격 포맷팅
            price_str = "가격 정보 없음"
            if price:
                price_str = f"{price:,}원"
                if product.get("discount_rate"):
                    price_str += f" (할인 {product['discount_rate']}%)"
            
            # 추천 이유 생성
            reason = self.generate_recommendation_reason(product, preferences)
            
            markdown += f"{idx}. **[{name}]:** ({price_str})\n\n"
            markdown += f"    * **추천 이유:** {reason}\n\n"
            
            # 이미지 링크가 있으면 추가
            if product.get("image_url"):
                markdown += f"    * 이미지: [{product['image_url']}]({product['image_url']})\n\n"
        
        return markdown


def main():
    """테스트용 메인 함수"""
    # 환경변수에서 API 키 로드
    tavily_api_key = os.getenv("TAVILY_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")
    
    if not tavily_api_key:
        print("⚠️ 환경변수 TAVILY_API_KEY를 설정해주세요.")
        return
    
    # 에이전트 생성
    try:
        agent = PreferenceBasedRecommendationAgent(
            tavily_api_key=tavily_api_key,
            openai_api_key=openai_api_key
        )
    except ValueError as e:
        print(f"⚠️ {e}")
        return
    
    # 테스트 쿼리
    preference = "미니멀리즘, 30만원대"
    
    print(f"📊 제품 추천 시작: {preference}\n")
    
    # 제품 추천 실행
    result = agent.recommend_products(preference)
    
    # 결과 출력
    print(result)


if __name__ == "__main__":
    main()

