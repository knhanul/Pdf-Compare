"""
가입설계서 PDF 파싱 및 전처리 모듈
머릿글/바닥글 제거, 섹션 구조 파싱
"""
import fitz  # PyMuPDF
import re
from typing import List, Dict, Tuple


class InsurancePDFParser:
    """가입설계서 PDF 파서"""
    
    # 머릿글/바닥글 Y좌표 범위
    HEADER_Y_MAX = 85  # 머릿글 최대 Y좌표
    FOOTER_Y_MIN = 750  # 바닥글 최소 Y좌표
    
    # 같은 라인으로 간주할 Y좌표 차이 임계값
    SAME_LINE_THRESHOLD = 5
    
    def __init__(self, pdf_path: str):
        """
        Args:
            pdf_path: PDF 파일 경로
        """
        self.pdf_path = pdf_path
        self.pdf_doc = fitz.open(pdf_path)
        self.pages = []
        
    def parse(self) -> List[Dict]:
        """
        PDF를 파싱하여 구조화된 데이터 반환
        
        Returns:
            페이지별 섹션 리스트
            [{
                'page': 페이지 번호,
                'sections': [섹션 리스트]
            }]
        """
        self.pages = []
        
        for page_num in range(len(self.pdf_doc)):
            page_data = self._parse_page(page_num)
            if page_data['sections']:  # 빈 페이지가 아닌 경우만 추가
                self.pages.append(page_data)
        
        return self.pages
    
    def _parse_page(self, page_num: int) -> Dict:
        """
        단일 페이지 파싱
        
        Args:
            page_num: 페이지 번호
            
        Returns:
            페이지 데이터
        """
        page = self.pdf_doc.load_page(page_num)
        blocks_data = page.get_text("dict")["blocks"]
        
        # 텍스트 블록 추출 (머릿글/바닥글 제외)
        text_blocks = []
        for block in blocks_data:
            if block['type'] == 0:  # 텍스트 블록
                for line in block['lines']:
                    line_text = "".join(span['text'] for span in line['spans']).strip()
                    if not line_text:
                        continue
                    
                    bbox = line['bbox']
                    y_pos = bbox[1]
                    
                    # 머릿글/바닥글 필터링
                    if y_pos < self.HEADER_Y_MAX or y_pos > self.FOOTER_Y_MIN:
                        continue
                    
                    first_span = line['spans'][0]
                    font_size = first_span['size']
                    is_bold = "bold" in first_span['font'].lower()
                    
                    text_blocks.append({
                        'text': line_text,
                        'bbox': bbox,
                        'y': y_pos,
                        'x': bbox[0],
                        'size': font_size,
                        'bold': is_bold
                    })
        
        # Y좌표 기준으로 정렬
        text_blocks.sort(key=lambda b: (b['y'], b['x']))
        
        # 섹션 구조화
        sections = self._structure_sections(text_blocks, page_num)
        
        return {
            'page': page_num,
            'sections': sections
        }
    
    def _structure_sections(self, text_blocks: List[Dict], page_num: int) -> List[Dict]:
        """
        텍스트 블록을 섹션 구조로 변환
        
        Args:
            text_blocks: 텍스트 블록 리스트
            page_num: 페이지 번호
            
        Returns:
            섹션 리스트
        """
        sections = []
        current_major_section = None  # ◆ 섹션
        current_minor_section = None  # ■ 섹션
        
        i = 0
        while i < len(text_blocks):
            block = text_blocks[i]
            text = block['text']
            
            # ◆ (큰 제목) 감지
            if '◆' in text:
                # 이전 섹션 저장
                if current_major_section:
                    sections.append(current_major_section)
                
                current_major_section = {
                    'type': 'major',
                    'title': text.replace('◆', '').strip(),
                    'page': page_num,
                    'bbox': block['bbox'],
                    'subsections': [],
                    'content': []
                }
                current_minor_section = None
                i += 1
                continue
            
            # ■ (섹션 제목) 감지
            if '■' in text:
                section_title = text.replace('■', '').strip()
                
                # 같은 라인의 다른 텍스트 수집 (설명)
                description_parts = [section_title]
                j = i + 1
                while j < len(text_blocks):
                    next_block = text_blocks[j]
                    # 같은 Y좌표 범위인지 확인
                    if abs(next_block['y'] - block['y']) <= self.SAME_LINE_THRESHOLD:
                        description_parts.append(next_block['text'])
                        j += 1
                    else:
                        break
                
                description = ' '.join(description_parts)
                
                current_minor_section = {
                    'type': 'minor',
                    'title': section_title,
                    'description': description,
                    'page': page_num,
                    'bbox': block['bbox'],
                    'content': []
                }
                
                if current_major_section:
                    current_major_section['subsections'].append(current_minor_section)
                else:
                    # ◆ 없이 ■만 있는 경우
                    sections.append(current_minor_section)
                
                i = j
                continue
            
            # 일반 본문 텍스트
            content_item = {
                'text': text,
                'bbox': block['bbox'],
                'page': page_num
            }
            
            if current_minor_section:
                current_minor_section['content'].append(content_item)
            elif current_major_section:
                current_major_section['content'].append(content_item)
            else:
                # 섹션 없는 독립 텍스트
                sections.append({
                    'type': 'standalone',
                    'text': text,
                    'bbox': block['bbox'],
                    'page': page_num
                })
            
            i += 1
        
        # 마지막 섹션 저장
        if current_major_section:
            sections.append(current_major_section)
        
        return sections
    
    def get_all_text_blocks(self) -> List[Dict]:
        """
        모든 텍스트 블록을 평탄화하여 반환 (비교용)
        
        Returns:
            텍스트 블록 리스트
        """
        all_blocks = []
        
        for page_data in self.pages:
            for section in page_data['sections']:
                all_blocks.extend(self._flatten_section(section))
        
        return all_blocks
    
    def _flatten_section(self, section: Dict) -> List[Dict]:
        """
        섹션을 평탄화하여 텍스트 블록 리스트로 변환
        
        Args:
            section: 섹션 데이터
            
        Returns:
            텍스트 블록 리스트
        """
        blocks = []
        
        if section['type'] == 'standalone':
            blocks.append({
                'text': section['text'],
                'bbox': section['bbox'],
                'page': section['page'],
                'section_type': 'standalone'
            })
        elif section['type'] == 'major':
            # 큰 제목
            blocks.append({
                'text': section['title'],
                'bbox': section['bbox'],
                'page': section['page'],
                'section_type': 'major_title'
            })
            
            # 본문
            for content in section['content']:
                blocks.append({
                    'text': content['text'],
                    'bbox': content['bbox'],
                    'page': content['page'],
                    'section_type': 'major_content',
                    'section_title': section['title']
                })
            
            # 하위 섹션
            for subsection in section['subsections']:
                blocks.extend(self._flatten_section(subsection))
        
        elif section['type'] == 'minor':
            # 섹션 제목 + 설명
            blocks.append({
                'text': section['description'],
                'bbox': section['bbox'],
                'page': section['page'],
                'section_type': 'minor_title',
                'section_title': section['title']
            })
            
            # 본문
            for content in section['content']:
                blocks.append({
                    'text': content['text'],
                    'bbox': content['bbox'],
                    'page': content['page'],
                    'section_type': 'minor_content',
                    'section_title': section['title']
                })
        
        return blocks
    
    def close(self):
        """PDF 문서 닫기"""
        if self.pdf_doc:
            self.pdf_doc.close()
