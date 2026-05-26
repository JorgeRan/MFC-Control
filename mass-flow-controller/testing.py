timestamp = "2026-02-25T17:39:08Z"

parded_timestamp = timestamp.strip('Z').split('T')
parsed_time = ""
for i in parded_timestamp:
    parsed_time += i
    parsed_time += " "
print(parsed_time)