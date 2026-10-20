#!/usr/bin/env python3
"""Replace the signing certificate in an unpacked adb-backup _manifest so it restores into our re-signed build.
usage: fix_manifest.py <unpacked_dir> <cert.hex>"""
import sys,os
d,certf=sys.argv[1],sys.argv[2]
p=os.path.join(d,'apps','com.checkbox.minershminer','_manifest')
m=open(p).read().split('\n'); cert=open(certf).read().strip()
open(p,'w').write('\n'.join(m[:6]+['1',cert,'']))
print('manifest signature replaced')
