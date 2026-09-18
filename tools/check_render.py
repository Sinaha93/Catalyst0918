import sys
import io
import zipfile
from pathlib import Path
import win32com.client
import pythoncom

root=Path(sys.argv[1]); out=root/'rendered';out.mkdir(exist_ok=True)
pythoncom.CoInitialize()
power=win32com.client.DispatchEx('PowerPoint.Application')
try:
    source=next((root/'outputs').glob('*.pptx'))
    deck=power.Presentations.Open(str(source),ReadOnly=True,Untitled=False,WithWindow=False)
    print('PPT slides',deck.Slides.Count,flush=True)
    deck.Export(str(out),'PNG',1300,900)
    deck.Close()
    with zipfile.ZipFile(source) as z:
        children=[n for n in z.namelist() if n.startswith('ppt/embeddings/') and n.endswith('.pptx')]
        for i,name in enumerate(children):
            path=root/f'child_{i}.pptx';path.write_bytes(z.read(name))
            deck=power.Presentations.Open(str(path),ReadOnly=True,Untitled=False,WithWindow=False)
            assert deck.Slides.Count==2
            if i==0: deck.Export(str(out/'child'),'PNG',1300,900)
            deck.Close()
        print('Embedded decks opened',len(children),flush=True)
finally:
    power.Quit()
    pythoncom.CoUninitialize()
