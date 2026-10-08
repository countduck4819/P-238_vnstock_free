"""Config-driven section taxonomy for financial page navigation."""
from __future__ import annotations

SECTION_TAXONOMY = {
    "balance_sheet": {
        "kind": "CORE",
        "aliases": (
            "bang can doi ke toan", "bang can doi ke toan hop nhat",
            "bao cao tinh hinh tai chinh", "statement of financial position",
            "balance sheet",
        ),
    },
    "income_statement": {
        "kind": "CORE",
        "aliases": (
            "bao cao ket qua hoat dong kinh doanh",
            "bao cao ket qua kinh doanh",
            "income statement", "statement of comprehensive income",
        ),
    },
    "cash_flow": {
        "kind": "CORE",
        "aliases": (
            "bao cao luu chuyen tien te", "bao cao luu chuyen tien te hop nhat",
            "cash flow statement", "statement of cash flows",
        ),
    },
    "cash_and_equivalents": {
        "kind": "IMPORTANT",
        "aliases": ("tien va tuong duong tien", "tien gui", "cash and cash equivalents"),
    },
    "financial_investments": {
        "kind": "IMPORTANT",
        "aliases": ("dau tu tai chinh", "chung khoan dau tu", "financial investments"),
    },
    "receivables": {
        "kind": "IMPORTANT",
        "aliases": ("phai thu", "phai thu khach hang", "phai thu khac", "du phong phai thu"),
    },
    "inventory": {"kind": "IMPORTANT", "aliases": ("hang ton kho", "inventory")},
    "fixed_assets": {
        "kind": "IMPORTANT",
        "aliases": ("tai san co dinh", "tai san vo hinh", "fixed assets"),
    },
    "investment_property": {
        "kind": "IMPORTANT",
        "aliases": ("bat dong san dau tu", "investment property"),
    },
    "construction_in_progress": {
        "kind": "IMPORTANT",
        "aliases": ("chi phi xay dung co ban do dang", "construction in progress"),
    },
    "long_term_assets": {"kind": "IMPORTANT", "aliases": ("tai san dai han", "long term assets")},
    "debt_and_borrowings": {
        "kind": "IMPORTANT",
        "aliases": (
            "vay va no", "cac khoan vay", "no vay", "no thue tai chinh",
            "trai phieu", "debt and borrowings",
        ),
    },
    "payables": {"kind": "IMPORTANT", "aliases": ("phai tra", "phai tra nguoi ban", "payables")},
    "equity": {
        "kind": "IMPORTANT",
        "aliases": ("von chu so huu", "von gop", "loi nhuan chua phan phoi", "equity"),
    },
    "revenue_note": {
        "kind": "IMPORTANT",
        "aliases": (
            "doanh thu", "doanh thu ban hang", "doanh thu cung cap dich vu",
            "doanh thu ban hang va cung cap dich vu", "doanh thu thuan", "revenue",
        ),
    },
    "cost_and_expenses": {
        "kind": "IMPORTANT",
        "aliases": (
            "gia von", "chi phi tai chinh", "chi phi lai vay", "chi phi ban hang",
            "chi phi quan ly doanh nghiep", "thu nhap khac", "chi phi khac",
            "chi phi thue thu nhap doanh nghiep", "chi phi thue tndn",
        ),
    },
    "profit_and_eps": {
        "kind": "IMPORTANT",
        "aliases": ("loi nhuan", "eps", "lai co ban tren co phieu", "profit", "earnings per share"),
    },
    "related_parties": {
        "kind": "IMPORTANT",
        "aliases": ("giao dich voi ben lien quan", "cac ben lien quan", "related parties"),
    },
    "segments": {
        "kind": "IMPORTANT",
        "aliases": ("phan khuc", "bo phan kinh doanh", "segment reporting"),
    },
}

SKIP_ALIASES = (
    "muc luc", "table of contents", "cong bo thong tin", "gioi thieu doanh nghiep",
    "bao cao ban giam doc", "bao cao quan tri", "chinh sach ke toan",
    "accounting policies", "chu ky", "chu ky", "signature",
)


def taxonomy_items():
    return SECTION_TAXONOMY.items()
