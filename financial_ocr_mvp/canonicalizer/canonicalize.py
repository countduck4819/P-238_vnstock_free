import json
import os


# =========================
# PATH
# =========================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)


INPUT_FILE = os.path.join(
    BASE_DIR,
    "output",
    "validated",
    "page_005_table_validated.json"
)


OUTPUT_FILE = os.path.join(
    BASE_DIR,
    "output",
    "canonical",
    "FPT",
    "Q1_2015",
    "financial_fact.json"
)



# =========================
# DOCUMENT METADATA
# =========================

DOCUMENT_INFO = {

    "ticker": "FPT",

    "document_id": "FPT_Q1_2015",

    "source_pdf": "FPT_Q1_2015.pdf",

    "report_period": "Q1_2015",

    "company_name": "Công ty Cổ phần FPT",

    "exchange": "HOSE"

}



# =========================
# NORMALIZE NUMBER
# =========================

def normalize_value(raw):

    """
    Chuyển raw_value thành số để phân tích.

    Giữ nguyên raw_value.
    Không sửa dữ liệu gốc.
    """

    if raw is None:
        return None


    raw = str(raw).strip()



    # trường hợp số âm dạng (100.000)

    if raw.startswith("(") and raw.endswith(")"):

        number = raw.replace(
            ".",
            ""
        )

        number = number.replace(
            "(",
            "-"
        )

        number = number.replace(
            ")",
            ""
        )


        try:
            return int(number)

        except:
            return None



    # số bình thường

    try:

        return int(
            raw.replace(
                ".",
                ""
            )
        )

    except:

        return None




# =========================
# CONVERT
# =========================

def convert(data):


    # validator đang bọc trong validated_data
    validated = data.get(
        "validated_data",
        data
    )



    canonical = {


        # =====================
        # DOCUMENT
        # =====================

        "document": DOCUMENT_INFO,



        # =====================
        # STATEMENT
        # =====================

        "statement": {


            "statement_type":

            validated.get(
                "table_type",
                "unknown"
            ),


            "table_name":

            validated.get(
                "table_name",
                ""
            ),


            "period":

            validated.get(
                "period",
                ""
            ),


            "unit":

            validated.get(
                "unit",
                ""
            )

        },



        # =====================
        # ROWS
        # =====================

        "rows":[]

    }




    rows = validated.get(
        "rows",
        []
    )



    for row in rows:



        row_data = {


            "row_name":

            row.get(
                "row_name"
            ),



            "row_code":

            row.get(
                "row_code"
            ),



            "cells":[]

        }




        for cell in row.get(
            "cells",
            []
        ):



            raw = cell.get(
                "raw_value"
            )



            cell_data = {



                "column":

                cell.get(
                    "column"
                ),



                "raw_value":

                raw,



                "normalized_value":

                normalize_value(
                    raw
                ),



                "source":{


                    "pdf":

                    DOCUMENT_INFO[
                        "source_pdf"
                    ],



                    "page":

                    "5",



                    "table":

                    validated.get(
                        "table_name",
                        ""
                    ),



                    "row":

                    row.get(
                        "row_name"
                    ),



                    "column":

                    cell.get(
                        "column"
                    ),



                    "method":

                    "Qwen2.5-VL-3B-Instruct",



                    "confidence":

                    cell.get(
                        "confidence",
                        "unknown"
                    )

                }

            }



            row_data["cells"].append(
                cell_data
            )



        canonical["rows"].append(
            row_data
        )



    return canonical




# =========================
# RUN
# =========================


with open(
    INPUT_FILE,
    encoding="utf-8"
) as f:

    data = json.load(f)




result = convert(
    data
)



os.makedirs(
    os.path.dirname(
        OUTPUT_FILE
    ),
    exist_ok=True
)




with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as f:


    json.dump(

        result,

        f,

        ensure_ascii=False,

        indent=2

    )



print(
    "Saved:",
    OUTPUT_FILE
)