from PIL import Image


img = Image.open(
    "images/page_005_table.png"
)


upscale = img.resize(
    (
        img.width*2,
        img.height*2
    )
)


upscale.save(
    "images/page_005_table_x2.png"
)