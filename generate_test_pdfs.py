import fitz

def create_pdf(filename, text):
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), text, fontsize=20)
    doc.save(filename)
    print(f"Created {filename}")

if __name__ == "__main__":
    create_pdf("test_left.pdf", "Hello World. This is a test document using PyMuPDF.")
    create_pdf("test_right.pdf", "Hello World. This is a different test document using PyMuPDF.")
