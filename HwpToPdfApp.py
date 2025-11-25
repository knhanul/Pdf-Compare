import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
import os
import shutil
import sys
import win32com.client
import pythoncom
import threading
import time

class HwpToPdfApp:
    def __init__(self, root):
        self.root = root
        self.root.title("한글(HWP) -> PDF 일괄 변환기")
        self.root.geometry("600x500")

        # --- 변수 초기화 ---
        self.input_mode = tk.StringVar(value="file") # 'file' or 'dir'
        self.input_path = tk.StringVar()
        self.output_dir = tk.StringVar()
        
        # --- UI 구성 ---
        self.create_widgets()

    def create_widgets(self):
        # 1. 입력 선택 영역
        input_frame = tk.LabelFrame(self.root, text="입력 설정", padx=10, pady=10)
        input_frame.pack(fill="x", padx=10, pady=5)

        # 라디오 버튼 (파일 vs 폴더)
        tk.Radiobutton(input_frame, text="파일 하나만 변환", variable=self.input_mode, value="file", command=self.toggle_mode).pack(anchor="w")
        tk.Radiobutton(input_frame, text="폴더 전체 변환 (일괄)", variable=self.input_mode, value="dir", command=self.toggle_mode).pack(anchor="w")

        # 경로 입력 및 찾기 버튼
        path_frame = tk.Frame(input_frame)
        path_frame.pack(fill="x", pady=5)
        
        self.entry_input = tk.Entry(path_frame, textvariable=self.input_path)
        self.entry_input.pack(side="left", fill="x", expand=True, padx=(0, 5))
        
        self.btn_browse_input = tk.Button(path_frame, text="파일 찾기", command=self.browse_input)
        self.btn_browse_input.pack(side="right")

        # 2. 저장 폴더 설정 영역
        output_frame = tk.LabelFrame(self.root, text="저장 폴더 설정 (비워두면 원본 위치에 저장)", padx=10, pady=10)
        output_frame.pack(fill="x", padx=10, pady=5)

        path_out_frame = tk.Frame(output_frame)
        path_out_frame.pack(fill="x", pady=5)

        self.entry_output = tk.Entry(path_out_frame, textvariable=self.output_dir)
        self.entry_output.pack(side="left", fill="x", expand=True, padx=(0, 5))

        tk.Button(path_out_frame, text="폴더 찾기", command=self.browse_output).pack(side="right")

        # 3. 실행 버튼
        self.btn_convert = tk.Button(self.root, text="PDF 변환 시작", command=self.start_conversion, bg="#4CAF50", fg="white", font=("Arial", 12, "bold"))
        self.btn_convert.pack(fill="x", padx=10, pady=10)

        # 4. 로그 영역
        log_frame = tk.LabelFrame(self.root, text="진행 상황", padx=10, pady=10)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, state='disabled', height=10)
        self.log_text.pack(fill="both", expand=True)

    def toggle_mode(self):
        """라디오 버튼 선택에 따라 버튼 텍스트 변경"""
        if self.input_mode.get() == "file":
            self.btn_browse_input.config(text="파일 찾기")
        else:
            self.btn_browse_input.config(text="폴더 찾기")

    def browse_input(self):
        if self.input_mode.get() == "file":
            path = filedialog.askopenfilename(filetypes=[("한글 파일", "*.hwp *.hwpx")])
        else:
            path = filedialog.askdirectory()
        
        if path:
            self.input_path.set(path)

    def browse_output(self):
        path = filedialog.askdirectory()
        if path:
            self.output_dir.set(path)

    def log(self, message):
        """로그 창에 메시지 출력"""
        self.log_text.config(state='normal')
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state='disabled')

    def clear_com_cache(self):
        """win32com gen_py 캐시 삭제 (오류 해결용)"""
        try:
            # win32com 모듈 경로 확인
            gen_py_path = os.path.join(os.path.abspath(os.path.dirname(win32com.__file__)), "gen_py")
            if os.path.exists(gen_py_path):
                shutil.rmtree(gen_py_path)
                self.log("기존 COM 캐시(gen_py)를 삭제했습니다. (초기화)")
            
            # 사용자 temp 폴더의 gen_py도 확인 (가상환경 사용시 위치가 다를 수 있음)
            temp_gen_py = os.path.join(os.environ.get('LOCALAPPDATA'), 'Temp', 'gen_py')
            if os.path.exists(temp_gen_py):
                shutil.rmtree(temp_gen_py)
        except Exception as e:
            self.log(f"캐시 삭제 중 경고 (무시 가능): {e}")

    def start_conversion(self):
        """별도 스레드에서 변환 시작"""
        input_path = self.input_path.get()
        if not input_path:
            messagebox.showwarning("경고", "입력 파일/폴더를 선택해주세요.")
            return

        self.btn_convert.config(state="disabled", text="변환 중...")
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')

        # 스레드 실행
        thread = threading.Thread(target=self.run_process)
        thread.start()

    def run_process(self):
        """실제 변환 로직 (스레드 내부)"""
        pythoncom.CoInitialize()
        
        # 1. 중요: 실행 전 캐시 정리
        self.clear_com_cache()

        try:
            input_mode = self.input_mode.get()
            source_path = self.input_path.get()
            target_dir = self.output_dir.get()

            # 변환할 파일 리스트
            files_to_convert = []
            if input_mode == "file":
                if os.path.isfile(source_path):
                    files_to_convert.append(source_path)
            else:
                for root, dirs, files in os.walk(source_path):
                    for file in files:
                        if file.lower().endswith(('.hwp', '.hwpx')):
                            files_to_convert.append(os.path.join(root, file))

            if not files_to_convert:
                self.log("변환할 HWP 파일이 없습니다.")
                return

            self.log(f"총 {len(files_to_convert)}개의 파일을 발견했습니다. 한글 프로그램을 시작합니다...")

            # 한글 프로그램 실행
            hwp = None
            try:
                # gencache를 사용하여 초기화
                hwp = win32com.client.gencache.EnsureDispatch("HWPFrame.HwpObject")
                hwp.RegisterModule("FilePathCheckDLL", "FilePathCheckerModule") 
                hwp.XHwpWindows.Item(0).Visible = True 
            except Exception as e:
                self.log(f"한글 프로그램 실행 실패: {e}")
                self.log("팁: '관리자 권한'으로 실행해보거나, 한글 프로그램이 이미 켜져 있다면 모두 종료 후 다시 시도하세요.")
                return

            success_count = 0
            
            for i, file_path in enumerate(files_to_convert):
                try:
                    self.log(f"[{i+1}/{len(files_to_convert)}] 변환 시도: {os.path.basename(file_path)}")
                    
                    file_dir = os.path.dirname(file_path)
                    file_name = os.path.basename(file_path)
                    file_root, _ = os.path.splitext(file_name)
                    
                    save_dir = target_dir if target_dir else file_dir
                    save_dir = os.path.abspath(save_dir)
                    if not os.path.exists(save_dir):
                        os.makedirs(save_dir)
                        
                    pdf_path = os.path.join(save_dir, f"{file_root}.pdf")

                    # 파일 열기
                    if hwp.Open(file_path):
                        time.sleep(1.5) # 대기 시간 조금 더 늘림
                        
                        try:
                            act = hwp.CreateAction("FileSaveAs_S")
                            
                            # 액션 생성 실패 시 재시도 (가끔 타이밍 이슈)
                            if act is None:
                                time.sleep(0.5)
                                act = hwp.CreateAction("FileSaveAs_S")

                            if act is None:
                                self.log("  -> 오류: 'FileSaveAs_S' 액션 생성 실패. (보안 승인 팝업이 떠있는지 확인하세요)")
                                hwp.Clear(1)
                                continue

                            pset = act.CreateSet()
                            act.GetDefault(pset)
                            pset.SetItem("FileName", pdf_path)
                            pset.SetItem("Format", "PDF")
                            
                            if act.Execute(pset):
                                success_count += 1
                                self.log(f"  -> 변환 성공")
                            else:
                                self.log("  -> 변환 실패 (Execute False)")
                                
                        except Exception as save_err:
                            self.log(f"  -> 저장 오류: {save_err}")
                            
                    else:
                        self.log("  -> 파일 열기 실패")
                    
                except Exception as e:
                    self.log(f"  -> 처리 중 오류: {e}")
                finally:
                    if hwp:
                        hwp.Clear(1)

            self.log("-" * 30)
            self.log(f"작업 완료: 성공 {success_count} / 실패 {len(files_to_convert) - success_count}")
            if hwp:
                hwp.Quit()

        except Exception as e:
            self.log(f"치명적 오류 발생: {e}")
        
        finally:
            pythoncom.CoUninitialize()
            self.root.after(0, lambda: self.btn_convert.config(state="normal", text="PDF 변환 시작"))
            self.root.after(0, lambda: messagebox.showinfo("완료", "작업이 종료되었습니다."))

if __name__ == "__main__":
    root = tk.Tk()
    app = HwpToPdfApp(root)
    root.mainloop()