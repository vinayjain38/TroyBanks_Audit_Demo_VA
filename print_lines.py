import linecache

fn = 'src/Utils/upload.py'
for i in range(150, 166):
    print(i, repr(linecache.getline(fn, i)))
