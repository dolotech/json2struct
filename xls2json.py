from pathlib import Path
import json
import xlrd
import codecs
import sys, getopt

def is_number(s):
    try:
        float(s)  # 如果能转换float，说明是个数字
        return True
    except ValueError:
        pass  # 占位符

    try:
        import unicodedata  # 引入Unicodedata模块
        unicodedata.numeric(s)  # 如果能转成numeric，说明是个数字
        return True
    except (TypeError, ValueError):
        pass

    return False


def parseValue(value):
    if is_number(value):
        return ('%f' % value).rstrip('0').rstrip('.')
    else:
        if len(value) > 1 and value[0] == '[' and value[-1] == ']':
            return value.replace('=', ':',-1)
        elif len(value) > 1 and value[0] == '{' and value[-1] == '}':
            return value.replace('{', '[',-1).replace('}', ']',-1)
        else:
            return '"%s"' % value

def parseJson(root_dir='./xls', store_dir='"./json"'):
    path = Path(root_dir)

    all_json_file = list(path.glob('**/*.xlsm'))
    for json_file in all_json_file:
        if json_file.name.find("~$") != -1:  # 忽略文件打开时的临时文件
            continue
        with xlrd.open_workbook(json_file) as wb:
            dic = []
            sh = wb.sheet_by_index(0)  # sheet页
            title = sh.row_values(2)

            if len(str(title[0]).strip()) == 0:
                continue
            for rownum in range(3, sh.nrows):
                rowvalue = sh.row_values(rownum)
                single = ''

                id = rowvalue[0]
                if is_number(id):
                    single += '"%s" : { ' % int(id)
                else:
                    if len(str(id).strip()) == 0:
                        continue
                    single += '"%s" : %s' % (id, parseValue(rowvalue[1]))
                    dic.append(single)
                    continue

                for colnum in range(1, len(rowvalue)):
                    value = rowvalue[colnum]
                    if len(str(value).strip()) == 0:
                        continue
                    key = str(title[colnum])
                    # 忽略id列和空行
                    if key == 'id' or len(key.strip()) == 0:
                        continue
                    single += '"%s" : %s, ' % (key, parseValue(value))
                single = single[:-2]
                single += '}'
                dic.append(single)
            # sheet页名+ Data.json 作为生成文件的名字
            with codecs.open(store_dir + '/' + sh.name + 'Data.json', "w", "utf-8") as f:
                j = "\n{\n    "
                j += '\n    ,'.join(dic)
                f.write(j + "\n}")


def main(argv):
    inputfile = ''
    outputfile = ''
    try:
        opts, args = getopt.getopt(argv, "hi:o:", ["ifile=", "ofile="])
    except getopt.GetoptError:
        print('xls2json.py -i <inputfile> -o <outputfile>')
        sys.exit(2)
    for opt, arg in opts:
        if opt == '-h':
            print('xls2json.py -i <inputfile> -o <outputfile>')
            sys.exit()
        elif opt in ("-i", "--ifile"):
            inputfile = arg
        elif opt in ("-o", "--ofile"):
            outputfile = arg

    print('输入的文件为:', inputfile)
    print('输出的文件为:', outputfile)
    parseJson(inputfile, outputfile)
    print('恭喜生成完成!!')


if __name__ == '__main__':
    main(sys.argv[1:])
