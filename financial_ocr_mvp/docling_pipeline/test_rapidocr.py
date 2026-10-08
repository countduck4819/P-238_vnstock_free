from rapidocr_onnxruntime import RapidOCR
import sys


IMAGE = sys.argv[1]


ocr = RapidOCR()


result, elapse = ocr(IMAGE)


print("TIME:", elapse)


if result:
    for item in result:
        print(item)
else:
    print("NO TEXT")