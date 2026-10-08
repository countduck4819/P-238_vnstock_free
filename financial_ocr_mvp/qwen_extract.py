import torch
import json

from PIL import Image

from transformers import (
    Qwen2_5_VLForConditionalGeneration,
    AutoProcessor
)


MODEL_NAME = "Qwen/Qwen2.5-VL-3B-Instruct"


IMAGE_PATH = "images/page_005.png"


OUTPUT = "output/page_005.json"


# =========================
# Load model
# =========================

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


# =========================
# Load image
# =========================

image = Image.open(
    IMAGE_PATH
).convert("RGB")


# =========================
# Prompt
# =========================

prompt = """

Bạn là Financial Document Extraction Engine.

Đọc trang báo cáo tài chính này.

Chỉ lấy dữ liệu nhìn thấy.

Không:
- suy luận
- tính toán
- sửa số
- chuẩn hóa tên chỉ tiêu


Nếu có bảng tài chính:

Trích xuất:

- tên bảng
- header
- rows
- cells
- giá trị từng ô


Trả về JSON:


{
"page_number":"",
"document_type":"",
"company_name":"",
"report_title":"",
"tables":[]
}


Chỉ trả JSON.

"""


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


inputs = inputs.to(model.device)


# =========================
# Generate
# =========================

with torch.no_grad():

    output = model.generate(
        **inputs,
        max_new_tokens=3000
    )


response = processor.batch_decode(
    output,
    skip_special_tokens=True
)


result = response[0]


print(result)


# lưu raw output

with open(
    OUTPUT,
    "w",
    encoding="utf-8"
) as f:

    f.write(result)