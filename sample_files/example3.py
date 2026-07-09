def process_data(data_list):
    # This function is intentionally duplicated for jscpd
    processed = []
    for item in data_list:
        if item is not None:
            processed.append(item * 2)
    return processed

def another_function():
    x = 1
    y = 2
    z = x + y
    return z
