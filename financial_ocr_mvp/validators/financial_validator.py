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
    "raw",
    "page_005_table.json"
)


OUTPUT_FILE = os.path.join(
    BASE_DIR,
    "output",
    "validated",
    "page_005_table_validated.json"
)



# =========================
# REQUIRED FIELDS
# =========================

REQUIRED_FIELDS = [

    "document_type",

    "table_name",

    "rows"

]



# =========================
# VALIDATE
# =========================

def validate(data):


    errors = []


    # check required fields

    for field in REQUIRED_FIELDS:

        if field not in data:

            errors.append(

                {

                    "type":
                    "missing_field",

                    "field":
                    field

                }

            )



    # validate rows

    rows = data.get(
        "rows",
        []
    )


    if not isinstance(
        rows,
        list
    ):

        errors.append(

            {

                "type":
                "invalid_type",

                "field":
                "rows"

            }

        )



    # validate row structure

    for i, row in enumerate(rows):


        if "row_name" not in row:

            errors.append(

                {

                    "type":
                    "missing_row_name",

                    "row":
                    i

                }

            )



        if "cells" not in row:

            errors.append(

                {

                    "type":
                    "missing_cells",

                    "row":
                    i

                }

            )



    return {


        "status":

        "passed"

        if len(errors) == 0

        else "warning",



        "errors":

        errors,



        # QUAN TRỌNG
        # giữ nguyên toàn bộ table

        "validated_data":

        data

    }




# =========================
# RUN
# =========================


with open(
    INPUT_FILE,
    encoding="utf-8"
) as f:

    data = json.load(f)



result = validate(
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