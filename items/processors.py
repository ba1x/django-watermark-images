import numpy as np

from io import BytesIO
from pickle import dump, load, UnpicklingError

from django.conf import settings
from imagekit import ImageSpec, register
from PIL import Image, ImageDraw, ImageFont, ImageMath


_default_font = ImageFont.truetype('/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf', 24)


def add_text_overlay(image, text, font=_default_font):
    rgba_image = image.convert('RGBA')
    text_overlay = Image.new('RGBA', rgba_image.size, (255, 255, 255, 0))
    image_draw = ImageDraw.Draw(text_overlay)
    text_size_x, text_size_y = image_draw.textsize(text, font=font)
    text_xy = ((rgba_image.size[0] / 2) - (text_size_x / 2), (rgba_image.size[1] / 2) - (text_size_y / 2))
    image_draw.text(text_xy, text, font=font, fill=(255, 255, 255, 128))
    image_with_text_overlay = Image.alpha_composite(rgba_image, text_overlay)

    return image_with_text_overlay


def add_watermark(image, watermark, text, font=_default_font):
    rgba_image = image.convert('RGBA')

    # WATERMARK
    rgba_watermark = watermark.convert('RGBA')

    image_x, image_y = rgba_image.size
    watermark_x, watermark_y = rgba_watermark.size

    # Determine the scale size of the watermark
    temp_image = image_x/image_y
    temp_watermark = watermark_x/watermark_y
    temp = temp_watermark / temp_image

    # If watermark landscape
    if temp_watermark > 1:
    
        # The constant value below only works if:
        #  - watermark image has width > height
        #  - temp_watermark > temp_image
        constant_value = 1.071

    # If watermark portrait
    else:

        # The constant value below still need improvement
        #   - some images do not fit
        constant_value = 5.419

    # watermark fit to width
    scale_size = constant_value * temp

    watermark_scale = max(image_x / (scale_size * watermark_x), image_y / (scale_size * watermark_y))
    new_size = (int(watermark_x * watermark_scale), int(watermark_y * watermark_scale))
    rgba_watermark = rgba_watermark.resize(new_size)

    rgba_watermark_mask = rgba_watermark.convert("L").point(lambda x: min(x, 90))
    rgba_watermark.putalpha(rgba_watermark_mask)

    watermark_x, watermark_y = rgba_watermark.size
    rgba_image.paste(rgba_watermark, ((image_x - watermark_x) // 2, (image_y - watermark_y) // 2), rgba_watermark_mask)

    # TEXT OVERLAY
    text_overlay = Image.new('RGBA', rgba_image.size, (255, 255, 255, 0))
    image_draw = ImageDraw.Draw(text_overlay)
    text_size_x, text_size_y = image_draw.textsize(text, font=font)
    # Header
    text_position_header = 0.015
    text_xy_header = ((rgba_image.size[0] / 2) - (text_size_x / 2), text_position_header * ((rgba_image.size[1]) - (text_size_y)))
    image_draw.text(text_xy_header, text, font=font, fill=(255, 255, 255, 128)) 
    # Footer
    text_position_footer = 0.99
    text_xy_footer = ((rgba_image.size[0] / 2) - (text_size_x / 2), text_position_footer * ((rgba_image.size[1]) - (text_size_y)))
    image_draw.text(text_xy_footer, text, font=font, fill=(255, 255, 255, 128))
    # Text Overlay
    image_with_text_overlay = Image.alpha_composite(rgba_image, text_overlay)

    return image_with_text_overlay


def lsb_encode(data, image):
    bytes_io = BytesIO()
    dump(data, file=bytes_io)
    data_bytes = bytes_io.getvalue()
    data_bytes_array = np.fromiter(data_bytes, dtype=np.uint8)
    data_bits_list = np.unpackbits(data_bytes_array).tolist()
    data_bits_list += [0] * (image.size[0] * image.size[1] - len(data_bits_list))
    watermark = Image.frombytes(data=bytes(data_bits_list), size=image.size, mode='L')
    red, green, blue = image.split()
    watermarked_red = ImageMath.eval("convert(a&0xFE|b&0x1,'L')", a=red, b=watermark)
    watermarked_image = Image.merge("RGB", (watermarked_red, green, blue))
    return watermarked_image


def lsb_decode(image):
    try:
        red, green, blue = image.split()
        watermark = ImageMath.eval("(a&0x1)*0x01", a=red)
        watermark = watermark.convert('L')
        watermark_bytes = bytes(watermark.getdata())
        watermark_bits_array = np.fromiter(watermark_bytes, dtype=np.uint8)
        watermark_bytes_array = np.packbits(watermark_bits_array)
        watermark_bytes = bytes(watermark_bytes_array)
        bytes_io = BytesIO(watermark_bytes)
        return load(bytes_io)
    except UnpicklingError:
        return ''


class TextOverlayProcessor(object):
    font = ImageFont.truetype('/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf', 36)

    def process(self, image):
        text_overlay = settings.WATERMARK_TEXT
        return add_text_overlay(image, text_overlay, font=self.font)


class WatermarkProcessor(object):
    watermark = Image.open(settings.WATERMARK_IMAGE)

    def process(self, image):
        text_overlay = settings.WATERMARK_TEXT
        return add_watermark(image, self.watermark, text_overlay)


class HiddenWatermarkProcessor(object):
    def process(self, image):
        return lsb_encode('django-watermark-images', image)


class TextOverlay(ImageSpec):
    processors = [TextOverlayProcessor()]
    format = 'JPEG'
    options = {'quality': 75}


class Watermark(ImageSpec):
    processors = [WatermarkProcessor()]
    format = 'JPEG'
    options = {'quality': 75}


class HiddenWatermark(ImageSpec):
    processors = [HiddenWatermarkProcessor()]
    format = 'PNG'


register.generator('items:text-overlay', TextOverlay)
register.generator('items:watermark', Watermark)
register.generator('items:hidden-watermark', HiddenWatermark)
