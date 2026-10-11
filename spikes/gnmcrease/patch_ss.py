p = "/mnt/data/hifipushie/gnmcrease/shapesolve.py"
s = open(p).read()
s = s.replace('S = np.arange(0.5, 8.01, 0.5)', 'S = np.arange(0.5, float(os.environ.get("SMAX", "8")) + 0.01, 0.5)\nCURV = float(os.environ.get("CURV", "0"))   # sigma (mm) on the sections\' second differences (the fold\'s crest); 0 = off')
s = s.replace('''            r += list(((a - b) / SIG).ravel()) if a is not None and b is not None else [20.0] * (2 * len(S))''',
              '''            r += list(((a - b) / SIG).ravel()) if a is not None and b is not None else [20.0] * (2 * len(S))
            if CURV:
                r += list(((np.diff(a, 2, axis=0) - np.diff(b, 2, axis=0)) / CURV).ravel()) if a is not None and b is not None else [20.0] * (2 * len(S) - 4)''')
s = s.replace('''    nsec = 3 * 2 * len(S)''', '''    nsec = 3 * 2 * len(S)    # (the shape rms printed is over the first section's points + curvature terms when CURV)''')
open(p, "w").write(s)
print("ok")
