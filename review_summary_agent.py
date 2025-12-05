"""
무신사 쇼핑 도움 에이전트 - 리뷰 기반 제품 장단점 요약
Tavily API를 사용하여 무신사 제품 리뷰 텍스트를 수집하고, 텍스트 분석을 통해 장단점을 주제별로 요약합니다.
"""

import os
import re
from typing import List, Dict, Optional
from tavily import TavilyClient
import json


class ReviewSummaryAgent:
    """제품 리뷰를 수집하고 장단점을 요약하는 에이전트"""
    
    # 핵심 주제 카테고리
    TOPIC_CATEGORIES = [
        "핏", "소재", "배송/교환", "내구성", "색상", 
        "디자인", "가격", "품질", "사이즈", "착용감"
    ]
    
    def __init__(self, tavily_api_key: Optional[str] = None):
        """
        Args:
            tavily_api_key: Tavily API 키. 없으면 환경변수 TAVILY_API_KEY에서 로드
        """
        self.tavily_api_key = tavily_api_key or os.getenv("TAVILY_API_KEY")
        if not self.tavily_api_key:
            raise ValueError("Tavily API 키가 필요합니다. 환경변수 TAVILY_API_KEY를 설정하거나 tavily_api_key 파라미터를 제공하세요.")
        
        self.tavily_client = TavilyClient(api_key=self.tavily_api_key)
    
    def collect_reviews(self, product_name: str) -> List[str]:
        """
        Tavily API를 사용하여 무신사 도메인에서만 제품 리뷰 텍스트를 수집합니다.
        무신사 내에서 다양한 키워드로 넓은 범위의 리뷰를 수집합니다.
        
        Args:
            product_name: 제품명
            
        Returns:
            수집된 무신사 리뷰 텍스트 리스트
        """
        # 무신사 도메인 전용 리뷰 검색 쿼리 (다양한 키워드 조합으로 확대)
        musinsa_queries = [
            # 기본 무신사 리뷰 검색
            f"{product_name} site:musinsa.com 후기",
            f"{product_name} site:musinsa.com 리뷰",
            f"{product_name} site:musinsa.com",
            f"site:musinsa.com {product_name} 후기",
            f"site:musinsa.com {product_name} 리뷰",
            
            # 리뷰 유형별 검색
            f"{product_name} 무신사 실제 후기 site:musinsa.com",
            f"{product_name} 무신사 구매 후기 site:musinsa.com",
            f"{product_name} 무신사 사용 후기 site:musinsa.com",
            f"{product_name} 무신사 단점 위주 리뷰 site:musinsa.com",
            f"{product_name} 무신사 장점 리뷰 site:musinsa.com",
            
            # 리뷰 키워드 조합
            f"{product_name} 무신사 리뷰 모음 site:musinsa.com",
            f"{product_name} 무신사 리뷰 모음집 site:musinsa.com",
            f"{product_name} 무신사 상품평 site:musinsa.com",
            f"{product_name} 무신사 평가 site:musinsa.com",
            
            # 검색어 변형
            f"musinsa.com {product_name} 후기",
            f"무신사 {product_name} 리뷰 site:musinsa.com",
        ]
        
        musinsa_reviews = []
        seen_urls = set()
        
        # 무신사 도메인에서만 리뷰 수집 (더 많은 결과 수집)
        for query in musinsa_queries:
            try:
                response = self.tavily_client.search(
                    query=query,
                    search_depth="advanced",
                    max_results=20  # 결과 수 증가
                )
                
                if response and "results" in response:
                    for result in response["results"]:
                        content = result.get("content", "")
                        url = result.get("url", "").lower()
                        
                        # 무신사 도메인만 허용 (엄격한 필터링)
                        is_musinsa_domain = (
                            "musinsa.com" in url or
                            url.startswith("https://www.musinsa.com") or
                            url.startswith("http://www.musinsa.com") or
                            url.startswith("https://musinsa.com") or
                            url.startswith("http://musinsa.com")
                        )
                        
                        # 무신사 도메인이면서 중복되지 않은 리뷰만 수집
                        if content and is_musinsa_domain and url not in seen_urls:
                            seen_urls.add(url)
                            musinsa_reviews.append(content)
                            
            except Exception as e:
                print(f"검색 중 오류 발생 ({query}): {e}")
                continue
        
        if not musinsa_reviews:
            print(f"⚠️ '{product_name}'에 대한 무신사 리뷰를 찾을 수 없습니다.")
        else:
            print(f"✅ 무신사에서 {len(musinsa_reviews)}개의 리뷰를 찾았습니다.")
        
        return musinsa_reviews
    
    def analyze_reviews(self, reviews: List[str], product_name: str) -> Dict:
        """
        텍스트 분석을 사용하여 리뷰를 분석하고 장단점을 주제별로 분류합니다.
        
        Args:
            reviews: 수집된 리뷰 텍스트 리스트
            product_name: 제품명
            
        Returns:
            장단점 분석 결과 딕셔너리
        """
        if not reviews:
            return {
                "pros": [],
                "cons": []
            }
        
        # 리뷰 텍스트를 하나로 합침 (너무 길면 자름)
        combined_reviews = "\n\n".join(reviews)
        
        # 텍스트 자름 (약 4000자)
        if len(combined_reviews) > 4000:
            combined_reviews = combined_reviews[:4000] + "..."
        
        return self._analyze_with_basic_method(combined_reviews)
    
    def _analyze_with_basic_method(self, reviews_text: str) -> Dict:
        """
        텍스트 분석 방법으로 리뷰를 분석합니다.
        
        Args:
            reviews_text: 리뷰 텍스트
            
        Returns:
            장단점 분석 결과
        """
        pros = []
        cons = []
        
        # 긍정/부정 키워드
        positive_keywords = [
            "좋", "만족", "최고", "추천", "편안", "트렌디", "예쁘", "깔끔",
            "튼튼", "오래", "딱", "완벽", "훌륭", "훌륭", "빠르", "친절"
        ]
        
        negative_keywords = [
            "아쉽", "불만", "별로", "작", "크", "안 좋", "부족", "어둡",
            "밝", "이상", "문제", "불편", "느리", "느슨", "빠지", "낡"
        ]
        
        # 주제별 키워드 매핑
        topic_keywords = {
            "핏": ["핏", "착용", "입", "맞", "사이즈"],
            "소재": ["소재", "재질", "원단", "천", "세탁"],
            "배송/교환": ["배송", "교환", "반품", "포장", "발송"],
            "내구성": ["내구", "튼튼", "오래", "빨리", "낡"],
            "색상": ["색", "컬러", "어둡", "밝", "색감"],
            "디자인": ["디자인", "스타일", "예쁘", "깔끔", "심플"],
            "가격": ["가격", "비싸", "저렴", "할인", "가성비"],
            "품질": ["품질", "퀄리티", "좋", "나쁜", "완성도"],
            "사이즈": ["사이즈", "크", "작", "치수", "S/M/L"],
            "착용감": ["착용감", "편안", "불편", "딱", "느슨"]
        }
        
        # 리뷰를 문장 단위로 분리
        sentences = re.split(r'[.!?]\s+', reviews_text)
        
        pros_by_topic = {}
        cons_by_topic = {}
        
        for sentence in sentences:
            if len(sentence) < 10:  # 너무 짧은 문장 제외
                continue
            
            sentence_lower = sentence.lower()
            
            # 긍정/부정 판단
            positive_count = sum(1 for keyword in positive_keywords if keyword in sentence_lower)
            negative_count = sum(1 for keyword in negative_keywords if keyword in sentence_lower)
            
            # 주제 분류
            topic = None
            for topic_name, keywords in topic_keywords.items():
                if any(keyword in sentence_lower for keyword in keywords):
                    topic = topic_name
                    break
            
            if not topic:
                topic = "기타"
            
            # 긍정 의견
            if positive_count > negative_count and len(sentence) < 100:
                if topic not in pros_by_topic:
                    pros_by_topic[topic] = []
                if len(pros_by_topic[topic]) < 3:
                    pros_by_topic[topic].append(sentence.strip())
            
            # 부정 의견
            elif negative_count > positive_count and len(sentence) < 100:
                if topic not in cons_by_topic:
                    cons_by_topic[topic] = []
                if len(cons_by_topic[topic]) < 3:
                    cons_by_topic[topic].append(sentence.strip())
        
        # 결과 정리
        for topic, sentences_list in pros_by_topic.items():
            for sentence in sentences_list[:2]:  # 주제당 최대 2개
                pros.append({
                    "topic": topic,
                    "summary": sentence[:50]  # 요약
                })
        
        for topic, sentences_list in cons_by_topic.items():
            for sentence in sentences_list[:2]:  # 주제당 최대 2개
                cons.append({
                    "topic": topic,
                    "summary": sentence[:50]  # 요약
                })
        
        return {
            "pros": pros[:5],  # 최대 5개
            "cons": cons[:5]   # 최대 5개
        }
    
    def summarize_reviews(self, product_name: str) -> str:
        """
        제품 리뷰를 수집하고 장단점을 요약하여 마크다운 형식으로 반환합니다.
        
        Args:
            product_name: 제품명
            
        Returns:
            마크다운 형식의 장단점 요약
        """
        print(f"🔍 '{product_name}' 리뷰 수집 중...")
        
        # 리뷰 수집
        reviews = self.collect_reviews(product_name)
        
        if not reviews:
            return f"⚠️ '{product_name}'에 대한 리뷰를 찾을 수 없습니다."
        
        print(f"  → {len(reviews)}개의 리뷰 수집 완료")
        print(f"📊 리뷰 분석 중...")
        
        # 리뷰 분석
        analysis = self.analyze_reviews(reviews, product_name)
        
        # 마크다운 형식으로 변환
        return self._generate_markdown_summary(product_name, analysis)
    
    def _generate_markdown_summary(self, product_name: str, analysis: Dict) -> str:
        """
        분석 결과를 마크다운 형식으로 생성합니다.
        
        Args:
            product_name: 제품명
            analysis: 분석 결과 딕셔너리
            
        Returns:
            마크다운 형식의 요약
        """
        pros = analysis.get("pros", [])
        cons = analysis.get("cons", [])
        
        # 장점 리스트 생성
        pros_list = []
        for item in pros[:5]:  # 최대 5개
            topic = item.get("topic", "기타")
            summary = item.get("summary", "")
            pros_list.append(f"* **[{topic}]:** {summary}")
        
        # 단점 리스트 생성
        cons_list = []
        for item in cons[:5]:  # 최대 5개
            topic = item.get("topic", "기타")
            summary = item.get("summary", "")
            cons_list.append(f"* **[{topic}]:** {summary}")
        
        # 마크다운 형식 생성
        markdown = f"""### ✅ {product_name} 사용자 리뷰 기반 장단점 요약

#### 👍 주요 장점 (3-5가지)

"""
        
        if pros_list:
            markdown += "\n".join(pros_list)
        else:
            markdown += "* 리뷰에서 장점을 찾을 수 없습니다."
        
        markdown += "\n\n#### 👎 유의할 점 (3-5가지)\n\n"
        
        if cons_list:
            markdown += "\n".join(cons_list)
        else:
            markdown += "* 리뷰에서 단점을 찾을 수 없습니다."
        
        markdown += "\n"
        
        return markdown


def main():
    """테스트용 메인 함수"""
    # 환경변수에서 API 키 로드
    tavily_api_key = os.getenv("TAVILY_API_KEY")
    
    if not tavily_api_key:
        print("⚠️ 환경변수 TAVILY_API_KEY를 설정해주세요.")
        return
    
    # 에이전트 생성
    try:
        agent = ReviewSummaryAgent(tavily_api_key=tavily_api_key)
    except ValueError as e:
        print(f"⚠️ {e}")
        return
    
    # 테스트 쿼리
    product_name = "나이키 에어맥스"
    
    print(f"📊 제품 리뷰 분석 시작: {product_name}\n")
    
    # 리뷰 요약 실행
    result = agent.summarize_reviews(product_name)
    
    # 결과 출력
    print(result)


if __name__ == "__main__":
    main()

