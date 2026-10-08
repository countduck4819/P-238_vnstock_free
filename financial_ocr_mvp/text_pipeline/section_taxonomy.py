from __future__ import annotations

SECTION_ALIASES = {
    "document_cover": ("bao cao tai chinh", "financial statements"),
    "table_of_contents": ("muc luc", "contents"),
    "management_report": ("bao cao cua ban giam doc", "bao cao ban giam doc"),
    "audit_report": ("bao cao kiem toan doc lap", "y kien kiem toan", "independent auditors report"),
    "balance_sheet": ("bang can doi ke toan", "bao cao tinh hinh tai chinh", "bang can doi"),
    "income_statement": ("bao cao ket qua hoat dong kinh doanh", "bao cao ket qua kinh doanh"),
    "cash_flow": ("bao cao luu chuyen tien te", "luu chuyen tien te"),
    "notes": ("ban thuyet minh bao cao tai chinh", "thuyet minh bao cao tai chinh"),
    "accounting_policy": ("chinh sach ke toan", "accounting policies"),
    "company_information": ("thong tin chung ve cong ty", "company information"),
    "related_parties": ("cac ben lien quan", "giao dich voi cac ben lien quan"),
    "borrowings": ("cac khoan vay", "vay va no"),
    "receivables": ("phai thu khach hang", "cac khoan phai thu"),
    "inventory": ("hang ton kho",), "fixed_assets": ("tai san co dinh",),
    "investments": ("dau tu tai chinh",), "payables": ("phai tra nguoi ban",),
    "equity": ("von chu so huu",), "revenue_notes": ("doanh thu",),
    "cost_notes": ("gia von", "chi phi ban hang"), "financial_income_expense": ("chi phi tai chinh",),
    "tax": ("thue thu nhap doanh nghiep",), "eps": ("lai co ban tren co phieu", "eps"),
}
CORE = {"balance_sheet", "income_statement", "cash_flow", "notes", "audit_report"}
