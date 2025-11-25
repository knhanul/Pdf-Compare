"""
비교 로직 테스트 스크립트
"""
from pdf_parser import InsurancePDFParser
from text_comparator import TextComparator
import json


def main():
    print("=" * 80)
    print("가입설계서 비교 프로그램 테스트")
    print("=" * 80)
    print()
    
    # 파일 경로
    pdf_a = "/home/ubuntu/insurance_compare/New건강클리닉2종(일반형)_원본.pdf"
    pdf_b = "/home/ubuntu/insurance_compare/New건강클리닉2종(일반형).pdf"
    
    # 1. PDF 파싱
    print("1. PDF 파싱 중...")
    parser_a = InsurancePDFParser(pdf_a)
    pages_a = parser_a.parse()
    print(f"   템플릿 파일: {len(pages_a)}개 페이지 파싱 완료")
    
    parser_b = InsurancePDFParser(pdf_b)
    pages_b = parser_b.parse()
    print(f"   생성본 파일: {len(pages_b)}개 페이지 파싱 완료")
    print()
    
    # 2. 섹션 구조 확인
    print("2. 섹션 구조 분석")
    print("-" * 80)
    
    total_sections_a = sum(len(page['sections']) for page in pages_a)
    total_sections_b = sum(len(page['sections']) for page in pages_b)
    print(f"   템플릿 파일 총 섹션 수: {total_sections_a}")
    print(f"   생성본 파일 총 섹션 수: {total_sections_b}")
    print()
    
    # 첫 페이지 섹션 샘플 출력
    if pages_a:
        print("   [템플릿 파일 첫 페이지 섹션 샘플]")
        for i, section in enumerate(pages_a[0]['sections'][:3]):
            if section['type'] == 'major':
                print(f"   ◆ {section['title']}")
                if section['subsections']:
                    for sub in section['subsections'][:2]:
                        print(f"      ■ {sub['title']}")
            elif section['type'] == 'minor':
                print(f"   ■ {section['title']}")
    print()
    
    # 3. 텍스트 블록 추출
    print("3. 텍스트 블록 추출")
    print("-" * 80)
    blocks_a = parser_a.get_all_text_blocks()
    blocks_b = parser_b.get_all_text_blocks()
    print(f"   템플릿 파일: {len(blocks_a)}개 텍스트 블록")
    print(f"   생성본 파일: {len(blocks_b)}개 텍스트 블록")
    print()
    
    # 블록 샘플 출력
    print("   [텍스트 블록 샘플 - 템플릿]")
    for i, block in enumerate(blocks_a[:5]):
        print(f"   {i+1}. [{block['section_type']}] {block['text'][:60]}...")
    print()
    
    # 4. 비교 수행
    print("4. 단어 단위 비교 수행")
    print("-" * 80)
    comparator = TextComparator()
    results = comparator.compare_blocks(blocks_a, blocks_b)
    diff_count = comparator.get_diff_count(results)
    
    print(f"   총 차이점: {diff_count['total']}개")
    print(f"   - 변경됨: {diff_count['modified']}개")
    print(f"   - 삭제됨: {diff_count['deleted']}개")
    print(f"   - 추가됨: {diff_count['added']}개")
    print()
    
    # 5. 차이점 상세 정보
    print("5. 차이점 상세 정보 (샘플)")
    print("-" * 80)
    
    # 변경된 항목 샘플
    if results['modified']:
        print("   [변경된 항목 샘플]")
        for i, item in enumerate(results['modified'][:3]):
            word_diff = item['word_diff']
            print(f"\n   변경 {i+1}:")
            print(f"   원본: {item['block_a']['text'][:80]}...")
            print(f"   생성: {item['block_b']['text'][:80]}...")
            if word_diff['deleted']:
                print(f"   삭제된 단어: {', '.join(word_diff['deleted'][:10])}")
            if word_diff['added']:
                print(f"   추가된 단어: {', '.join(word_diff['added'][:10])}")
        print()
    
    # 삭제된 항목 샘플
    if results['deleted']:
        print("   [삭제된 항목 샘플]")
        for i, item in enumerate(results['deleted'][:3]):
            print(f"   삭제 {i+1}: {item['block_a']['text'][:80]}...")
        print()
    
    # 추가된 항목 샘플
    if results['added']:
        print("   [추가된 항목 샘플]")
        for i, item in enumerate(results['added'][:3]):
            print(f"   추가 {i+1}: {item['block_b']['text'][:80]}...")
        print()
    
    # 6. 하이라이트 정보
    print("6. 하이라이트 정보")
    print("-" * 80)
    highlight_pages_a = len(results['diff_highlights_a'])
    highlight_pages_b = len(results['diff_highlights_b'])
    total_highlights_a = sum(len(h) for h in results['diff_highlights_a'].values())
    total_highlights_b = sum(len(h) for h in results['diff_highlights_b'].values())
    
    print(f"   템플릿 파일: {highlight_pages_a}개 페이지에 {total_highlights_a}개 하이라이트")
    print(f"   생성본 파일: {highlight_pages_b}개 페이지에 {total_highlights_b}개 하이라이트")
    print()
    
    # 색상별 집계
    colors_a = {'red': 0, 'yellow': 0, 'green': 0}
    colors_b = {'red': 0, 'yellow': 0, 'green': 0}
    
    for highlights in results['diff_highlights_a'].values():
        for h in highlights:
            colors_a[h['color']] += 1
    
    for highlights in results['diff_highlights_b'].values():
        for h in highlights:
            colors_b[h['color']] += 1
    
    print("   [템플릿 파일 색상별]")
    print(f"   🔴 빨간색(삭제): {colors_a['red']}개")
    print(f"   🟡 노란색(변경): {colors_a['yellow']}개")
    print(f"   🟢 초록색(추가): {colors_a['green']}개")
    print()
    
    print("   [생성본 파일 색상별]")
    print(f"   🔴 빨간색(삭제): {colors_b['red']}개")
    print(f"   🟡 노란색(변경): {colors_b['yellow']}개")
    print(f"   🟢 초록색(추가): {colors_b['green']}개")
    print()
    
    # 정리
    parser_a.close()
    parser_b.close()
    
    print("=" * 80)
    print("테스트 완료!")
    print("=" * 80)


if __name__ == '__main__':
    main()
