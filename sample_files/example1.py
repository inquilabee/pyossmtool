def calculate_area(length, width):
    if length < 0 or width < 0:
        print("Length and width cannot be negative")
        return None
    area = length * width
    return area

def calculate_perimeter(length, width):
    if length < 0 or width < 0:
        print("Length and width cannot be negative")
        return None
    perimeter = 2 * (length + width)
    return perimeter

def complex_function(a, b, c, d):
    if a > 0:
        if b > 0:
            if c > 0:
                if d > 0:
                    return a + b + c + d
                else:
                    return a + b + c
            else:
                return a + b
        else:
            return a
    else:
        return 0
