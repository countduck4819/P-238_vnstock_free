import torch
import json
import os

from PIL import Image

from transformers import (
    Qwen2_5_VLForConditionalGeneration,
    AutoProcessor
)


# ==================================================
# CONFIG
# ==================================================

MODEL_NAME = "Qwen/Qwen2.5-VL-3B-Instruct"


IMAGE_PATH = "images/page_005_table_x2.png"


OUTPUT_PATH = "output/raw/page_005_table_grid.json"


RAW_OUTPUT_PATH = "output/raw/page_005_grid_raw_response.txt"


# Metadata phục vụ truy xuất nguồn sau này

TICKER = "FPT"

PDF_NAME = "FPT_Q1_2015.pdf"

PAGE_NUMBER = "5"

TABLE_BBOX = "[120,300,2200,1250]"



os.makedirs(
    os.path.dirname(OUTPUT_PATH),
    exist_ok=True
)



# ==================================================
# LOAD MODEL
# ==================================================

print("Loading model...")


processor = AutoProcessor.from_pretrained(
    MODEL_NAME
)


model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
    MODEL_NAME,
    torch_dtype=torch.float16,
    device_map="auto"
)


model.eval()


print("Model loaded")



# ==================================================
# LOAD IMAGE
# ==================================================

image = Image.open(
    IMAGE_PATH
).convert("RGB")


print(
    "Image size:",
    image.size
)



# ==================================================
# PROMPT
# ==================================================

prompt = f"""
Read the financial table exactly as visible in the image.
Return only one JSON object with exactly these keys: grid, source.
The grid must contain every row, including the header, as arrays of cells in
left-to-right order. Preserve Vietnamese text, number punctuation, parentheses,
row order, and column order. Do not infer, calculate, correct spelling,
normalize, guess codes, merge rows, or create row_name/row_code/cells.
Unknown cells may be null or empty. source: page={PAGE_NUMBER}, method=Qwen2.5-VL-3B-Instruct.
Return JSON only. No markdown. No explanation.
"""


# ==================================================
# MESSAGE
# ==================================================


messages = [

    {
        "role":"user",

        "content":[

            {
                "type":"image",
                "image":image
            },

            {
                "type":"text",
                "text":prompt
            }

        ]

    }

]



text = processor.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True
)



inputs = processor(
    text=[text],
    images=[image],
    return_tensors="pt"
)


inputs = inputs.to(
    model.device
)



# ==================================================
# GENERATE
# ==================================================

print("Extracting...")


with torch.no_grad():

    output = model.generate(

        **inputs,

        max_new_tokens=4000,

        do_sample=False

    )



# Chỉ decode token do model sinh ra; không decode lại prompt.
# Nếu decode toàn bộ output, parser có thể chọn JSON template rỗng
# nằm trong prompt thay vì kết quả extraction thật.
generated_ids = output[:, inputs.input_ids.shape[1]:]

response = processor.batch_decode(
    generated_ids,
    skip_special_tokens=True
)[0]



print(response)



# ==================================================
# SAVE RAW RESPONSE
# ==================================================

with open(
    RAW_OUTPUT_PATH,
    "w",
    encoding="utf-8"
) as f:

    f.write(response)



# ==================================================
# CLEAN JSON
# ==================================================

def iter_json_objects(text):
    decoder = json.JSONDecoder()
    for start, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            yield value


def is_grid_table(value):
    return (
        isinstance(value, dict)
        and isinstance(value.get("grid"), list)
        and bool(value["grid"])
        and all(isinstance(row, list) for row in value["grid"])
    )


candidates = [value for value in iter_json_objects(response) if is_grid_table(value)]
if candidates:
    data = max(candidates, key=lambda value: len(json.dumps(value, ensure_ascii=False)))
    print("GRID JSON VALID")
else:
    data = {"error": "table grid extraction failed"}
    print("GRID JSON ERROR: no valid grid object found")


# ==================================================
# SAVE FINAL JSON
# ==================================================

with open(
    OUTPUT_PATH,
    "w",
    encoding="utf-8"
) as f:


    json.dump(

        data,

        f,

        ensure_ascii=False,

        indent=2

    )



print(
    "Saved:",
    OUTPUT_PATH
)