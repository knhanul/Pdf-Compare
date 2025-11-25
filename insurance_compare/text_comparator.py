"""
단어 단위 텍스트 비교 모듈
추가/삭제/변경 사항을 감지하고 시각화 데이터 생성
"""
import re
from difflib import SequenceMatcher, Differ
from typing import List, Dict, Tuple, Optional


class TextComparator:
    """텍스트 비교 클래스"""
    
    # 유사도 임계값 (블록 매칭용)
    SIMILARITY_THRESHOLD = 0.6
    
    def __init__(self):
        self.diff_results = []
        
    @staticmethod
    def normalize_text(text: str) -> str:
        """
        텍스트 정규화 (매칭용)
        
        Args:
            text: 원본 텍스트
            
        Returns:
            정규화된 텍스트
        """
        # 공백 정규화
        text = re.sub(r'\s+', ' ', text)
        # 특수문자 제거 (한글, 영문, 숫자만 남김)
        text = re.sub(r'[^\w\s가-힣]', '', text)
        return text.strip().lower()
    
    @staticmethod
    def tokenize_words(text: str) -> List[str]:
        """
        텍스트를 단어로 분리
        
        Args:
            text: 원본 텍스트
            
        Returns:
            단어 리스트
        """
        # 공백 정규화
        text = re.sub(r'\s+', ' ', text).strip()
        
        # 한글, 영문, 숫자, 특수문자를 고려한 토큰화
        # 공백으로 분리하되, 연속된 한글/영문/숫자는 하나의 단어로
        words = []
        current_word = ""
        
        for char in text:
            if char.isspace():
                if current_word:
                    words.append(current_word)
                    current_word = ""
            else:
                current_word += char
        
        if current_word:
            words.append(current_word)
        
        return words
    
    def find_best_match(self, target_block: Dict, source_blocks: List[Dict]) -> Optional[Tuple[int, float]]:
        """
        가장 유사한 블록 찾기
        
        Args:
            target_block: 대상 블록
            source_blocks: 소스 블록 리스트
            
        Returns:
            (매칭된 블록 인덱스, 유사도) 또는 None
        """
        target_norm = self.normalize_text(target_block['text'])
        if not target_norm:
            return None
        
        best_score = -1
        best_index = -1
        
        for i, block in enumerate(source_blocks):
            source_norm = self.normalize_text(block['text'])
            if not source_norm:
                continue
            
            # 섹션 타입이 같은 경우 가중치 부여
            type_bonus = 0.1 if target_block.get('section_type') == block.get('section_type') else 0
            
            score = SequenceMatcher(None, target_norm, source_norm).ratio() + type_bonus
            
            if score > best_score:
                best_score = score
                best_index = i
        
        if best_score >= self.SIMILARITY_THRESHOLD:
            return (best_index, best_score)
        
        return None
    
    def compare_word_level(self, text_a: str, text_b: str) -> Dict:
        """
        단어 단위 비교
        
        Args:
            text_a: 원본 텍스트
            text_b: 비교 텍스트
            
        Returns:
            비교 결과 딕셔너리
        """
        words_a = self.tokenize_words(text_a)
        words_b = self.tokenize_words(text_b)
        
        # 완전히 동일한 경우
        if words_a == words_b:
            return {
                'type': 'same',
                'added': [],
                'deleted': [],
                'changed': []
            }
        
        # difflib를 사용한 단어 단위 비교
        differ = Differ()
        diff = list(differ.compare(words_a, words_b))
        
        added = []
        deleted = []
        
        for line in diff:
            if line.startswith('+ '):
                added.append(line[2:])
            elif line.startswith('- '):
                deleted.append(line[2:])
        
        # 변경 사항이 있는 경우
        if added or deleted:
            return {
                'type': 'modified',
                'added': added,
                'deleted': deleted,
                'text_a': text_a,
                'text_b': text_b
            }
        
        return {
            'type': 'same',
            'added': [],
            'deleted': [],
            'changed': []
        }
    
    def compare_blocks(self, blocks_a: List[Dict], blocks_b: List[Dict]) -> Dict:
        """
        두 블록 리스트를 비교
        
        Args:
            blocks_a: 원본 블록 리스트
            blocks_b: 비교 블록 리스트
            
        Returns:
            비교 결과
        """
        results = {
            'modified': [],  # 변경된 블록
            'deleted': [],   # 삭제된 블록
            'added': [],     # 추가된 블록
            'sync_map': {},  # A -> B 매핑
            'diff_highlights_a': {},  # A의 하이라이트 (페이지별)
            'diff_highlights_b': {}   # B의 하이라이트 (페이지별)
        }
        
        matched_b_indices = set()
        
        # A의 각 블록에 대해 B에서 매칭 찾기
        for i, block_a in enumerate(blocks_a):
            match_result = self.find_best_match(block_a, blocks_b)
            
            if match_result:
                j, similarity = match_result
                
                # 이미 매칭된 블록은 건너뛰기
                if j in matched_b_indices:
                    continue
                
                matched_b_indices.add(j)
                results['sync_map'][i] = j
                
                block_b = blocks_b[j]
                
                # 단어 단위 비교
                word_diff = self.compare_word_level(block_a['text'], block_b['text'])
                
                if word_diff['type'] == 'modified':
                    # 변경된 블록
                    diff_info = {
                        'index_a': i,
                        'index_b': j,
                        'block_a': block_a,
                        'block_b': block_b,
                        'word_diff': word_diff
                    }
                    results['modified'].append(diff_info)
                    
                    # 하이라이트 정보 추가 (노란색)
                    page_a = block_a['page']
                    page_b = block_b['page']
                    
                    if page_a not in results['diff_highlights_a']:
                        results['diff_highlights_a'][page_a] = []
                    if page_b not in results['diff_highlights_b']:
                        results['diff_highlights_b'][page_b] = []
                    
                    # 상세 정보 생성
                    detail_a = self._format_diff_detail(word_diff, 'a')
                    detail_b = self._format_diff_detail(word_diff, 'b')
                    
                    results['diff_highlights_a'][page_a].append({
                        'bbox': block_a['bbox'],
                        'color': 'yellow',
                        'detail': detail_a
                    })
                    results['diff_highlights_b'][page_b].append({
                        'bbox': block_b['bbox'],
                        'color': 'yellow',
                        'detail': detail_b
                    })
            else:
                # 매칭되지 않음 = 삭제된 블록
                results['deleted'].append({
                    'index_a': i,
                    'block_a': block_a
                })
                
                # 하이라이트 정보 추가 (빨간색)
                page_a = block_a['page']
                if page_a not in results['diff_highlights_a']:
                    results['diff_highlights_a'][page_a] = []
                
                results['diff_highlights_a'][page_a].append({
                    'bbox': block_a['bbox'],
                    'color': 'red',
                    'detail': f"[삭제됨] {block_a['text']}"
                })
        
        # B에서 매칭되지 않은 블록 = 추가된 블록
        for j, block_b in enumerate(blocks_b):
            if j not in matched_b_indices:
                results['added'].append({
                    'index_b': j,
                    'block_b': block_b
                })
                
                # 하이라이트 정보 추가 (초록색)
                page_b = block_b['page']
                if page_b not in results['diff_highlights_b']:
                    results['diff_highlights_b'][page_b] = []
                
                results['diff_highlights_b'][page_b].append({
                    'bbox': block_b['bbox'],
                    'color': 'green',
                    'detail': f"[추가됨] {block_b['text']}"
                })
        
        return results
    
    def _format_diff_detail(self, word_diff: Dict, side: str) -> str:
        """
        차이점 상세 정보 포맷팅
        
        Args:
            word_diff: 단어 비교 결과
            side: 'a' 또는 'b'
            
        Returns:
            포맷팅된 문자열
        """
        if side == 'a':
            deleted = word_diff['deleted']
            if deleted:
                return f"[변경/삭제] {' '.join(deleted)}"
            else:
                return "[변경됨]"
        else:  # side == 'b'
            added = word_diff['added']
            if added:
                return f"[변경/추가] {' '.join(added)}"
            else:
                return "[변경됨]"
    
    def get_diff_count(self, results: Dict) -> Dict:
        """
        차이점 개수 집계
        
        Args:
            results: 비교 결과
            
        Returns:
            개수 딕셔너리
        """
        return {
            'modified': len(results['modified']),
            'deleted': len(results['deleted']),
            'added': len(results['added']),
            'total': len(results['modified']) + len(results['deleted']) + len(results['added'])
        }
