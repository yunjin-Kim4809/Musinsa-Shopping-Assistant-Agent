"""
무신사 쇼핑 도움 에이전트 - 실시간 가격 및 평점 비교 분석
Tavily API를 사용하여 무신사 제품의 가격, 평점, 스펙 정보를 우선적으로 수집하고 비교 분석합니다.
"""

import os
import re
from typing import List, Dict, Optional, Tuple
from tavily import TavilyClient
import json


class PriceRatingComparisonAgent:
    """제품 가격 및 평점 비교 분석을 수행하는 에이전트"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Args:
            api_key: Tavily API 키. 없으면 환경변수 TAVILY_API_KEY에서 로드
        """
        self.api_key = api_key or os.getenv("TAVILY_API_KEY")
        if not self.api_key:
            raise ValueError("Tavily API 키가 필요합니다. 환경변수 TAVILY_API_KEY를 설정하거나 api_key 파라미터를 제공하세요.")
        
        self.client = TavilyClient(api_key=self.api_key)
    
    def extract_product_names(self, query: str) -> List[str]:
        """
        입력 문자열에서 제품명을 추출합니다.
        예: "A 코트와 B 코트" -> ["A 코트", "B 코트"]
        
        Args:
            query: 비교 대상 제품 리스트 문자열
            
        Returns:
            추출된 제품명 리스트
        """
        # "와", "과", "vs", "VS", "," 등으로 분리
        separators = ["와", "과", " vs ", " VS ", ", ", ","]
        
        products = [query]
        for sep in separators:
            new_products = []
            for product in products:
                new_products.extend([p.strip() for p in product.split(sep) if p.strip()])
            products = new_products
        
        return products
    
    def search_product_info(self, product_name: str) -> Dict:
        """
        Tavily API를 사용하여 제품 정보를 검색합니다.
        무신사 정보를 우선적으로 검색합니다.
        
        Args:
            product_name: 제품명
            
        Returns:
            검색 결과 딕셔너리
        """
        # 무신사 우선 검색 쿼리
        musinsa_queries = [
            f"{product_name} 무신사 최저가",
            f"{product_name} 무신사 가격",
            f"{product_name} 무신사 할인",
            f"{product_name} 무신사 평점",
            f"{product_name} 무신사 리뷰",
            f"{product_name} 무신사 스펙",
            f"{product_name} site:musinsa.com"
        ]
        
        # 일반 검색 쿼리 (무신사 정보가 부족할 경우)
        general_queries = [
            f"{product_name} Musinsa lowest price",
            f"{product_name} online rating comparison",
            f"{product_name} 할인 가격"
        ]
        
        all_results = []
        musinsa_results = []
        
        # 먼저 무신사 검색 실행
        for query in musinsa_queries:
            try:
                response = self.client.search(
                    query=query,
                    search_depth="advanced",
                    max_results=5
                )
                
                if response and "results" in response:
                    for result in response["results"]:
                        # 무신사 관련 결과 우선 수집
                        url = result.get("url", "").lower()
                        content = result.get("content", "").lower()
                        if "musinsa" in url or "무신사" in content or "musinsa" in content:
                            musinsa_results.append(result)
                        else:
                            all_results.append(result)
            except Exception as e:
                print(f"검색 중 오류 발생 ({query}): {e}")
                continue
        
        # 무신사 결과가 충분하지 않으면 일반 검색 추가
        if len(musinsa_results) < 3:
            for query in general_queries:
                try:
                    response = self.client.search(
                        query=query,
                        search_depth="advanced",
                        max_results=3
                    )
                    
                    if response and "results" in response:
                        for result in response["results"]:
                            # 무신사 결과가 아닌 것만 추가
                            url = result.get("url", "").lower()
                            content = result.get("content", "").lower()
                            if "musinsa" not in url and "무신사" not in content and "musinsa" not in content:
                                all_results.append(result)
                except Exception as e:
                    print(f"검색 중 오류 발생 ({query}): {e}")
                    continue
        
        # 무신사 결과를 먼저 배치
        final_results = musinsa_results + all_results
        
        return {
            "product_name": product_name,
            "results": final_results
        }
    
    def extract_price_info(self, search_results: List[Dict]) -> Dict:
        """
        검색 결과에서 가격 정보를 추출합니다.
        무신사 정보를 우선적으로 추출합니다.
        
        Args:
            search_results: Tavily 검색 결과 리스트
            
        Returns:
            가격 정보 딕셔너리 (현재가격, 할인율, 배송비 등)
        """
        price_info = {
            "current_price": None,
            "original_price": None,
            "discount_rate": None,
            "shipping_cost": None,
            "final_price": None
        }
        
        # 무신사 결과를 우선적으로 처리
        musinsa_text = ""
        general_text = ""
        musinsa_urls = []
        
        for result in search_results:
            url = result.get("url", "").lower()
            content = result.get("content", "")
            if "musinsa" in url or "무신사" in content.lower() or "musinsa" in content.lower():
                musinsa_text += " " + content
                if "musinsa.com" in url:
                    musinsa_urls.append(result.get("url", ""))
            else:
                general_text += " " + content
        
        # 무신사 텍스트를 우선, 없으면 일반 텍스트 사용
        combined_text = musinsa_text if musinsa_text else general_text
        
        # 가격 추출 - 컨텍스트 기반으로 개선
        # 1단계: 명확한 가격 키워드와 함께 있는 가격 추출
        price_keywords = [
            r'(?:가격|판매가격|판매가|현재가격|현재가|최저가|할인가격|할인가|최종가격|최종가)\s*[:]?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*원',
            r'(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*원\s*(?:가격|판매가격|판매가|현재가격|할인가격)',
            r'price\s*[:]?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*원',
            r'₩\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(?:가격|price)',
            r'(?:원가|정가|할인전가격|할인 전 가격)\s*[:]?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*원',
        ]
        
        context_prices = []
        for pattern in price_keywords:
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            for match in matches:
                try:
                    price = int(match.replace(",", "").replace(".", ""))
                    if 5000 <= price <= 5000000:  # 합리적인 가격 범위 (5천원~500만원)
                        context_prices.append(price)
                except Exception:
                    continue
        
        # 2단계: 가격 패턴이 여러 번 나타나는 경우, 가장 큰 값을 현재가격으로 (할인 전 가격일 가능성)
        price_patterns = [
            r'(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*원',
            r'₩\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)',
        ]
        
        all_price_candidates = []
        for pattern in price_patterns:
            matches = re.finditer(pattern, combined_text)
            for match in matches:
                try:
                    price_str = match.group(1).replace(",", "").replace(".", "")
                    price = int(price_str)
                    
                    # 가격 범위 필터링
                    if not (5000 <= price <= 5000000):
                        continue
                    
                    # 컨텍스트 확인 - 가격과 관련 없는 숫자 제외
                    start = max(0, match.start() - 30)
                    end = min(len(combined_text), match.end() + 30)
                    context = combined_text[start:end].lower()
                    
                    # 제외할 키워드 (리뷰 수, 배송비, 평점 등)
                    exclude_keywords = [
                        '리뷰', 'review', '후기', '평점', 'rating', '점수', 'score',
                        '배송비', '배송', 'shipping', 'delivery',
                        '할인율', '할인', 'discount', 'dc',
                        '수량', 'quantity', '재고', 'stock',
                        '년', '월', '일', 'year', 'month', 'day'
                    ]
                    
                    # 제외 키워드가 가까이 있으면 스킵
                    skip = False
                    for keyword in exclude_keywords:
                        if keyword in context:
                            # 키워드가 가격 바로 앞뒤에 있으면 스킵
                            keyword_pos = context.find(keyword)
                            price_pos_in_context = match.start() - start
                            if abs(keyword_pos - price_pos_in_context) < 20:
                                skip = True
                                break
                    
                    if not skip:
                        # 가격 관련 키워드 확인
                        price_keywords_found = [
                            '가격', 'price', '원가', '정가', '판매가', '할인가',
                            '현재가', '최저가', '최종가'
                        ]
                        
                        has_price_keyword = any(kw in context for kw in price_keywords_found)
                        all_price_candidates.append((price, has_price_keyword, match.start()))
                        
                except Exception:
                    continue
        
        # 가격 후보 정렬: 키워드가 있는 가격 우선, 그 다음 위치 순서
        all_price_candidates.sort(key=lambda x: (not x[1], x[2]))
        
        # 컨텍스트 가격이 있으면 우선 사용
        if context_prices:
            price_info["current_price"] = min(context_prices)  # 할인가일 가능성이 높음
            price_info["final_price"] = min(context_prices)
        elif all_price_candidates:
            # 키워드가 있는 가격 우선 선택
            keyword_prices = [p[0] for p in all_price_candidates if p[1]]
            if keyword_prices:
                price_info["current_price"] = min(keyword_prices)
                price_info["final_price"] = min(keyword_prices)
            else:
                # 키워드가 없어도 가격처럼 보이는 것 중 적절한 선택
                prices = [p[0] for p in all_price_candidates]
                # 중복 제거 후 정렬
                sorted_prices = sorted(set(prices))
                
                if len(sorted_prices) >= 2:
                    # 여러 가격이 있으면 두 번째로 낮은 값 (첫 번째는 배송비일 수 있음)
                    price_info["current_price"] = sorted_prices[1] if sorted_prices[1] >= 5000 else sorted_prices[0]
                    price_info["final_price"] = price_info["current_price"]
                elif len(sorted_prices) == 1:
                    price_info["current_price"] = sorted_prices[0]
                    price_info["final_price"] = sorted_prices[0]
                else:
                    # 가격을 찾을 수 없음
                    pass
        
        # 원가(할인 전 가격) 추출
        original_price_patterns = [
            r'(?:원가|정가|할인전가격|할인 전 가격|기존가격)\s*[:]?\s*(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*원',
            r'(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*원\s*(?:원가|정가|할인전)',
        ]
        
        original_prices = []
        for pattern in original_price_patterns:
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            for match in matches:
                try:
                    price = int(match.replace(",", "").replace(".", ""))
                    if 5000 <= price <= 5000000:
                        original_prices.append(price)
                except Exception:
                    continue
        
        if original_prices:
            price_info["original_price"] = max(original_prices)  # 원가는 보통 할인가보다 큼
        elif price_info["current_price"]:
            # 원가가 없으면 할인율로 역산 시도
            pass  # 할인율 추출 후 처리
        
        # 할인율 패턴 추출
        discount_patterns = [
            r'(\d+)%\s*(?:할인|OFF|DC|discount)',
            r'(?:할인|discount)\s*(\d+)%',
            r'(\d+)%\s*↓',
        ]
        
        discount_rates = []
        for pattern in discount_patterns:
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            discount_rates.extend([int(match) for match in matches if match.isdigit() and 1 <= int(match) <= 99])
        
        if discount_rates:
            price_info["discount_rate"] = max(discount_rates)
        
        # 원가 계산 (할인율이 있고 원가가 없는 경우)
        if price_info["current_price"] and price_info["discount_rate"] and not price_info["original_price"]:
            original = price_info["current_price"] / (1 - price_info["discount_rate"] / 100)
            price_info["original_price"] = int(original)
        elif price_info["original_price"] and price_info["current_price"]:
            # 원가와 현재가가 모두 있으면 할인율 계산
            if price_info["original_price"] > price_info["current_price"]:
                discount = (1 - price_info["current_price"] / price_info["original_price"]) * 100
                price_info["discount_rate"] = round(discount, 1)
        
        # 배송비 추출
        shipping_patterns = [
            r'배송비\s*[:]?\s*(\d{1,3}(?:,\d{3})*)\s*원',
            r'배송\s*[:]?\s*(\d{1,3}(?:,\d{3})*)\s*원',
            r'무료배송',
            r'착불'
        ]
        
        if "무료배송" in combined_text or "무료 배송" in combined_text or "free shipping" in combined_text.lower():
            price_info["shipping_cost"] = 0
        elif "착불" in combined_text or "착불배송" in combined_text:
            price_info["shipping_cost"] = "착불"
        else:
            for pattern in shipping_patterns:
                matches = re.findall(pattern, combined_text, re.IGNORECASE)
                if matches:
                    try:
                        shipping = int(matches[0].replace(",", ""))
                        if shipping <= 50000:  # 합리적인 배송비 범위
                            price_info["shipping_cost"] = shipping
                            break
                    except Exception:
                        continue
        
        return price_info
    
    def extract_rating_info(self, search_results: List[Dict]) -> Dict:
        """
        검색 결과에서 평점 정보를 추출합니다.
        무신사 평점을 우선적으로 추출합니다.
        
        Args:
            search_results: Tavily 검색 결과 리스트
            
        Returns:
            평점 정보 딕셔너리
        """
        rating_info = {
            "musinsa_rating": None,
            "average_rating": None,
            "review_count": None
        }
        
        # 무신사 결과를 우선적으로 처리
        musinsa_text = ""
        general_text = ""
        
        for result in search_results:
            url = result.get("url", "").lower()
            content = result.get("content", "")
            if "musinsa" in url or "무신사" in content.lower() or "musinsa" in content.lower():
                musinsa_text += " " + content
            else:
                general_text += " " + content
        
        # 무신사 텍스트를 우선, 없으면 일반 텍스트 사용
        combined_text = musinsa_text if musinsa_text else general_text
        
        # 무신사 평점 패턴 (5점 만점) - 우선순위 높게
        musinsa_patterns = [
            r'무신사\s*평점\s*[:]\s*([\d.]+)\s*/?\s*5',
            r'Musinsa\s*평점\s*[:]\s*([\d.]+)\s*/?\s*5',
            r'무신사\s*([\d.]+)\s*/?\s*5',
            r'Musinsa\s*[:]\s*([\d.]+)\s*/?\s*5',
            r'평점\s*[:]\s*([\d.]+)\s*/?\s*5',
            r'([\d.]+)\s*점\s*/?\s*5'
        ]
        
        ratings = []
        for pattern in musinsa_patterns:
            matches = re.findall(pattern, combined_text)
            for match in matches:
                try:
                    rating = float(match)
                    if 0 <= rating <= 5:
                        ratings.append(rating)
                except Exception:
                    continue
        
        if ratings:
            rating_info["musinsa_rating"] = round(sum(ratings) / len(ratings), 2)
            rating_info["average_rating"] = rating_info["musinsa_rating"]
        
        # 리뷰 수 추출
        review_patterns = [
            r'리뷰\s*[:]?\s*(\d+)',
            r'후기\s*[:]?\s*(\d+)',
            r'review[s]?\s*[:]?\s*(\d+)'
        ]
        
        review_counts = []
        for pattern in review_patterns:
            matches = re.findall(pattern, combined_text, re.IGNORECASE)
            review_counts.extend([int(match) for match in matches if match.isdigit()])
        
        if review_counts:
            rating_info["review_count"] = max(review_counts)
        
        return rating_info
    
    def extract_specs(self, search_results: List[Dict]) -> str:
        """
        검색 결과에서 핵심 스펙을 추출합니다.
        
        Args:
            search_results: Tavily 검색 결과 리스트
            
        Returns:
            핵심 스펙 문자열
        """
        combined_text = " ".join([result.get("content", "") for result in search_results])
        
        # 스펙 키워드 추출
        spec_keywords = [
            "소재", "재질", "사이즈", "컬러", "디자인", "기능", "특징",
            "material", "size", "color", "design", "feature"
        ]
        
        specs = []
        lines = combined_text.split("\n")
        
        for line in lines[:20]:  # 처음 20줄만 확인
            for keyword in spec_keywords:
                if keyword in line and len(line) < 200:  # 너무 긴 줄 제외
                    specs.append(line.strip())
                    break
        
        if specs:
            return " | ".join(specs[:3])  # 상위 3개만 반환
        
        # 스펙을 찾지 못한 경우 검색 결과 요약
        if search_results:
            first_result = search_results[0].get("content", "")
            return first_result[:150] + "..." if len(first_result) > 150 else first_result
        
        return "스펙 정보 없음"
    
    def calculate_value_score(self, price_info: Dict, rating_info: Dict) -> float:
        """
        가격 대비 성능(가성비) 점수를 계산합니다.
        
        Args:
            price_info: 가격 정보 딕셔너리
            rating_info: 평점 정보 딕셔너리
            
        Returns:
            가성비 점수 (0-100)
        """
        score = 0.0
        
        # 가격 점수 (낮을수록 높은 점수, 50점 만점)
        if price_info.get("final_price"):
            price = price_info["final_price"]
            # 10만원 기준으로 정규화
            price_score = max(0, 50 - (price / 10000) * 0.5)
            score += price_score
        else:
            score += 25  # 가격 정보 없으면 중간 점수
        
        # 평점 점수 (높을수록 높은 점수, 50점 만점)
        if rating_info.get("musinsa_rating"):
            rating = rating_info["musinsa_rating"]
            rating_score = (rating / 5.0) * 50
            score += rating_score
        else:
            score += 25  # 평점 정보 없으면 중간 점수
        
        # 할인율 보너스 (최대 10점)
        if price_info.get("discount_rate"):
            discount = price_info["discount_rate"]
            discount_bonus = min(10, discount * 0.2)
            score += discount_bonus
        
        return round(score, 2)
    
    def compare_products(self, product_query: str) -> str:
        """
        제품들을 비교 분석하고 마크다운 테이블 형식으로 결과를 반환합니다.
        
        Args:
            product_query: 비교 대상 제품 리스트 (예: "A 코트와 B 코트")
            
        Returns:
            마크다운 테이블 형식의 비교 결과
        """
        # 제품명 추출
        product_names = self.extract_product_names(product_query)
        
        if len(product_names) < 2:
            return "⚠️ 비교할 제품이 최소 2개 이상 필요합니다."
        
        print(f"🔍 제품 정보 검색 중: {', '.join(product_names)}")
        
        # 각 제품 정보 수집
        products_data = []
        
        for product_name in product_names:
            print(f"  → {product_name} 검색 중...")
            
            # Tavily 검색
            search_data = self.search_product_info(product_name)
            
            # 정보 추출
            price_info = self.extract_price_info(search_data["results"])
            rating_info = self.extract_rating_info(search_data["results"])
            specs = self.extract_specs(search_data["results"])
            value_score = self.calculate_value_score(price_info, rating_info)
            
            products_data.append({
                "name": product_name,
                "price_info": price_info,
                "rating_info": rating_info,
                "specs": specs,
                "value_score": value_score
            })
        
        # 가성비 점수로 정렬
        products_data.sort(key=lambda x: x["value_score"], reverse=True)
        
        # 마크다운 테이블 생성
        return self._generate_markdown_table(products_data)
    
    def _generate_markdown_table(self, products_data: List[Dict]) -> str:
        """
        제품 비교 결과를 마크다운 테이블 형식으로 생성합니다.
        
        Args:
            products_data: 제품 정보 리스트
            
        Returns:
            마크다운 형식의 테이블 문자열
        """
        if len(products_data) < 2:
            return "⚠️ 비교할 제품이 부족합니다."
        
        product1 = products_data[0]
        product2 = products_data[1]
        
        # 가격 포맷팅
        def format_price(price_info):
            if price_info.get("final_price"):
                price_str = f"{price_info['final_price']:,}원"
                if price_info.get("discount_rate"):
                    price_str += f" (할인 {price_info['discount_rate']}%)"
                return price_str
            return "정보 없음"
        
        # 평점 포맷팅
        def format_rating(rating_info):
            if rating_info.get("musinsa_rating"):
                return f"{rating_info['musinsa_rating']} / 5점"
            return "정보 없음"
        
        # 추천 이유 생성
        def generate_recommendation(product_data, is_winner):
            reasons = []
            
            if is_winner:
                reasons.append("🏆 최종 추천")
            
            if product_data["value_score"]:
                reasons.append(f"가성비 점수: {product_data['value_score']:.1f}점")
            
            if product_data["price_info"].get("final_price"):
                reasons.append("저렴한 가격")
            
            if product_data["rating_info"].get("musinsa_rating"):
                if product_data["rating_info"]["musinsa_rating"] >= 4.0:
                    reasons.append("높은 평점")
            
            return " | ".join(reasons) if reasons else "-"
        
        # 최종 추천 제품 결정
        winner = product1 if product1["value_score"] > product2["value_score"] else product2
        winner_reason = f"가성비 점수 {winner['value_score']:.1f}점으로 우수함"
        
        if winner == product1:
            if product1["price_info"].get("final_price") and product2["price_info"].get("final_price"):
                if product1["price_info"]["final_price"] < product2["price_info"]["final_price"]:
                    winner_reason += ", 가격 경쟁력 있음"
            if product1["rating_info"].get("musinsa_rating") and product2["rating_info"].get("musinsa_rating"):
                if product1["rating_info"]["musinsa_rating"] > product2["rating_info"]["musinsa_rating"]:
                    winner_reason += ", 높은 평점"
        else:
            if product2["price_info"].get("final_price") and product1["price_info"].get("final_price"):
                if product2["price_info"]["final_price"] < product1["price_info"]["final_price"]:
                    winner_reason += ", 가격 경쟁력 있음"
            if product2["rating_info"].get("musinsa_rating") and product1["rating_info"].get("musinsa_rating"):
                if product2["rating_info"]["musinsa_rating"] > product1["rating_info"]["musinsa_rating"]:
                    winner_reason += ", 높은 평점"
        
        # 테이블 생성
        table = f"""### 🛍️ {product1['name']} vs {product2['name']} 실시간 비교 분석

| 항목 | {product1['name']} | {product2['name']} | 분석 및 추천 |
| :--- | :--- | :--- | :--- |
| **현재 가격** | {format_price(product1['price_info'])} | {format_price(product2['price_info'])} | |
| **무신사 평점** | {format_rating(product1['rating_info'])} | {format_rating(product2['rating_info'])} | |
| **핵심 스펙** | {product1['specs'][:100] + ('...' if len(product1['specs']) > 100 else '')} | {product2['specs'][:100] + ('...' if len(product2['specs']) > 100 else '')} | |
| **Agent 추천** | {generate_recommendation(product1, winner == product1)} | {generate_recommendation(product2, winner == product2)} | **최종 추천:** {winner['name']} - {winner_reason} |
"""
        
        return table


def main():
    """테스트용 메인 함수"""
    # 환경변수에서 API 키 로드
    api_key = os.getenv("TAVILY_API_KEY")
    
    if not api_key:
        print("⚠️ 환경변수 TAVILY_API_KEY를 설정해주세요.")
        return
    
    # 에이전트 생성
    agent = PriceRatingComparisonAgent(api_key=api_key)
    
    # 테스트 쿼리
    query = "나이키 에어 포스 1 07 W - 화이트와 푸마 터프패디드 FS 코듀로이"
    
    print(f"📊 제품 비교 분석 시작: {query}\n")
    
    # 비교 분석 실행
    result = agent.compare_products(query)
    
    # 결과 출력
    print(result)


if __name__ == "__main__":
    main()

