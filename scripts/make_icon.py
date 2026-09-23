"""Generate multi-resolution Nawam USB artwork. Pillow needed only for regeneration."""
from pathlib import Path
from PIL import Image, ImageDraw
ROOT = Path(__file__).resolve().parents[1]
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
s = 4
image = Image.new('RGBA', (256*s,256*s), (0,0,0,0))
d = ImageDraw.Draw(image)
d.rounded_rectangle((8*s,8*s,248*s,248*s), radius=52*s, fill='#070B14')
usb = Image.new('RGBA',image.size,(0,0,0,0)); d=ImageDraw.Draw(usb)
def rect(box, radius, fill): d.rounded_rectangle(tuple(x*s for x in box),radius=radius*s,fill=fill)
rect((96,31,160,98),8,'#D7E8E2')
rect((108,44,120,64),0,'#111A27');rect((136,44,148,64),0,'#111A27')
rect((78,82,178,223),25,'#10B981')
d.line([(91*s,111*s),(91*s,191*s),(96*s,204*s),(108*s,209*s)],fill='#2EE6A6',width=6*s)
for points in [[(128,176),(128,124)],[(128,150),(110,134)],[(128,159),(146,144),(146,131)]]:
    d.line([(x*s,y*s) for x,y in points],fill='#071C17',width=7*s,joint='curve')
d.polygon([(128*s,111*s),(118*s,126*s),(138*s,126*s)],fill='#071C17')
d.ellipse((120*s,173*s,136*s,189*s),fill='#071C17')
d.ellipse((103*s,126*s,115*s,138*s),fill='#071C17')
rect((140,119,153,132),2,'#071C17')
usb=usb.rotate(-34,resample=Image.Resampling.BICUBIC)
image.alpha_composite(usb)
image.save(ROOT/'res/nawam.ico',sizes=[(n,n) for n in SIZES])
image.resize((512,512),Image.Resampling.LANCZOS).save(ROOT/'res/nawam.png')
with Image.open(ROOT/'res/nawam.ico') as check: assert check.ico.sizes()=={(n,n) for n in SIZES}
print('USB icon generated',SIZES)
