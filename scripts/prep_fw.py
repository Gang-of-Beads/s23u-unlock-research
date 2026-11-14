import json, os, subprocess, tarfile, pathlib
D=pathlib.Path('/Users/chenyuanning/playground/samsung_s23ultra'); OUT=pathlib.Path('/tmp/fwimg'); OUT.mkdir(exist_ok=True)
m=json.load(open('/tmp/pitmap.json'))['map']
tars=sorted(D.glob('AP_*.tar.md5'))+sorted(D.glob('CP_*.tar.md5'))+sorted(D.glob('BL_*.tar.md5'))+sorted(D.glob('CSC_OXM*.tar.md5'))
plan=[]; unmapped=[]
for t in tars:
    print('==',t.name,flush=True)
    with tarfile.open(t) as tf:
        for mem in tf:
            if not mem.isfile(): continue
            base=os.path.basename(mem.name)
            if base.endswith('.lz4'): base=base[:-4]
            part=m.get(base.upper())
            if part is None and base.lower().endswith('.pit'): part='PIT'
            if part is None: unmapped.append(f'{t.name}:{mem.name}'); continue
            lz=mem.name.endswith('.lz4')
            target=OUT/(base+'.lz4' if lz else base)
            if not target.exists():
                src=tf.extractfile(mem)
                with open(target,'wb') as fh:
                    while True:
                        b=src.read(1<<22)
                        if not b: break
                        fh.write(b)
            if lz:
                dec=OUT/base
                if not dec.exists():
                    subprocess.run(['lz4','-d',str(target),str(dec)],check=True); target.unlink()
                plan.append((part,str(dec)))
            else: plan.append((part,str(target)))
json.dump({'plan':plan,'unmapped':unmapped}, open('/tmp/flashplan.json','w'), indent=1)
print('partitions:',len(plan)); print('unmapped:',unmapped)
