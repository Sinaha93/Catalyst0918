from pathlib import Path
import argparse
import PyInstaller.__main__

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser()
parser.add_argument('--name',default='촉매마감관리')
options=parser.parse_args()
templates=[next(root.glob('*촉매 마감.xlsx'))]
args=['--noconfirm','--onefile','--windowed','--name',options.name,'--distpath',str(root),'--workpath',str(root/'build'),'--specpath',str(root/'tools'),'--add-data',str(root/'frontend'/'dist')+';frontend/dist','--hidden-import','win32timezone','--hidden-import','pythoncom','--hidden-import','win32com.client']
for template in templates:args.extend(['--add-data',str(template)+';templates'])
PyInstaller.__main__.run(args+[str(root/'launcher.py')])
