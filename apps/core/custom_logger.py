# Custom decorator for logging function operations in the application
def logOperation(func):
    def wrapper(*args, **kwargs):
        print(f"Executing {func.__name__} function with arguments: {args} and keyword arguments: {kwargs}")
        result = func(*args, **kwargs)
        print(f"Finished executing {func.__name__} function with result: {result}")
        return result
    return wrapper