import linecache
filename='src/Utils/upload.py'
for i in range(150,162):
    line=linecache.getline(filename,i)
    print(i, repr(line))
