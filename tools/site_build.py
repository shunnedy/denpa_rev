#!/usr/bin/env python3
"""Assemble the static site (denpa-rev.asahina.net) from this repository.

    python3 tools/site_build.py /root/asahina-net-denpa-rev

Output: site/*.html, data/denpa-dict.json, a copy of the repo's docs/patches/
cheats/deploy/README under repo/ (served to the docs viewer), and a zip of
tools/. Nothing from the ROM is included.
"""
import datetime, os, shutil, sys, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    for f in ('index.html', 'editor.html', 'docs.html'):
        s = open(os.path.join(ROOT, 'site', f), encoding='utf-8').read()
        s = s.replace('BUILD_DATE', datetime.date.today().isoformat())
        open(os.path.join(out, f), 'w', encoding='utf-8').write(s)
    shutil.copy(os.path.join(ROOT, 'data', 'denpa-dict.json'), out)
    repo = os.path.join(out, 'repo')
    for d in ('docs', 'patches', 'cheats', 'deploy'):
        dst = os.path.join(repo, d)
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(os.path.join(ROOT, d), dst)
    shutil.copy(os.path.join(ROOT, 'README.md'), repo)
    with zipfile.ZipFile(os.path.join(out, 'denpa_rev-tools.zip'), 'w', zipfile.ZIP_DEFLATED) as z:
        for d in ('tools', 'data'):
            for fn in sorted(os.listdir(os.path.join(ROOT, d))):
                p = os.path.join(ROOT, d, fn)
                if os.path.isfile(p):
                    z.write(p, f'denpa_rev/{d}/{fn}')
        z.write(os.path.join(ROOT, 'README.md'), 'denpa_rev/README.md')
    print('site ->', out)
    for fn in sorted(os.listdir(out)):
        print('  ', fn)


if __name__ == '__main__':
    main()
