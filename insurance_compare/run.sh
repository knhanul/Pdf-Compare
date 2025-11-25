#!/bin/bash
# 가입설계서 비교 프로그램 실행 스크립트

echo "가입설계서 비교 프로그램을 시작합니다..."
echo ""

# 필수 패키지 확인
echo "필수 패키지 확인 중..."
python3 -c "import PyQt6" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "PyQt6가 설치되어 있지 않습니다. 설치 중..."
    pip3 install PyQt6 -q
fi

python3 -c "import fitz" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "PyMuPDF가 설치되어 있지 않습니다. 설치 중..."
    pip3 install pymupdf -q
fi

echo "패키지 확인 완료!"
echo ""

# 프로그램 실행
echo "GUI 프로그램을 실행합니다..."
python3 insurance_compare_gui.py

echo ""
echo "프로그램이 종료되었습니다."
