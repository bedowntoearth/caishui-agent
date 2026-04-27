import openpyxl
wb = openpyxl.load_workbook(
    r'e:\workspace\caishui-agent\backend\templates\admin\company_import_template.xlsx',
    read_only=True, data_only=True
)
rows = list(wb.active.iter_rows(values_only=True))
print("表头:", rows[0] if rows else 'EMPTY')
if len(rows) > 1:
    print("第2行:", rows[1])
else:
    print("无数据行")