import torch
from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor


model_name = "Qwen/Qwen2.5-VL-3B-Instruct"


print("Loading model...")


processor = AutoProcessor.from_pretrained(
    model_name
)


model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
    model_name,
    torch_dtype=torch.float16,
    device_map="auto"
)


print("Model loaded")

print(
    model.device
)