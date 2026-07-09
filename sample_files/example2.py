def process_data(data_list):
    # This function is intentionally duplicated for jscpd
    processed = []
    for item in data_list:
        if item is not None:
            processed.append(item * 2)
    return processed

def filter_data(data_list, threshold):
    filtered = []
    for item in data_list:
        if item > threshold:
            filtered.append(item)
    return filtered
