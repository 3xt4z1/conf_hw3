import json
import sys
import argparse


class ConfigError(Exception):
    pass


def evaluate_postfix_expression(tokens, constants):
    """Вычислить постфиксное выражение.
    Допустимые операции: +, -, *, max, abs
    Допустимо использовать имена констант (числа или массивы)
    и числа.
    """
    stack = []

    # Простая модель: все операции кроме max, abs бинарные и для чисел
    # max и abs - функции: max берет два аргумента, abs один аргумент
    # предположим, что для max и abs мы тоже ожидаем числа

    for t in tokens:
        if t in ['+', '-', '*']:
            if len(stack) < 2:
                raise ConfigError(f"Not enough operands for '{t}' operation.")
            b = stack.pop()
            a = stack.pop()
            if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
                raise ConfigError("Arithmetic operations are allowed only on numbers.")
            if t == '+':
                stack.append(a + b)
            elif t == '-':
                stack.append(a - b)
            elif t == '*':
                stack.append(a * b)
        elif t == 'max':
            # max - бинарная функция
            if len(stack) < 2:
                raise ConfigError("Not enough operands for max.")
            b = stack.pop()
            a = stack.pop()
            if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
                raise ConfigError("max is allowed only on numbers.")
            stack.append(max(a, b))
        elif t == 'abs':
            # abs - унарная функция
            if len(stack) < 1:
                raise ConfigError("Not enough operands for abs.")
            a = stack.pop()
            if not isinstance(a, (int, float)):
                raise ConfigError("abs is allowed only on numbers.")
            stack.append(abs(a))
        else:
            # это либо число, либо имя константы
            if t in constants:
                val = constants[t]
                # При вычислениях нужны только числа. Если массив, ошибка.
                if isinstance(val, list):
                    raise ConfigError(f"Cannot use array '{t}' in arithmetic expression.")
                stack.append(val)
            else:
                # возможно это число?
                try:
                    num = int(t)
                    stack.append(num)
                except ValueError:
                    raise ConfigError(f"Unknown token '{t}' in expression.")
    if len(stack) != 1:
        raise ConfigError("Invalid expression evaluation. Stack: " + str(stack))
    return stack[0]


def process_value(val, constants):
    """Рекурсивно преобразовать значение из JSON в конфигурационный язык.
    Если встретится строка вида '@(...)' - вычислить выражение."""
    if isinstance(val, dict):
        # Преобразуем каждый элемент словаря в выражение вида
        # по формату языка: словари отсутствуют в синтаксисе целевого языка
        # Задача не оговаривала, как преобразовывать словари кроме constants.
        # Можно решить, что словари запрещены, либо представить их как массив пар
        # или ещё какой-то формат. Предположим, что в входных данных словари встречаются
        # только в "constants", и на верхнем уровне.
        raise ConfigError("Dictionaries not allowed outside 'constants'.")
    elif isinstance(val, list):
        # Массив
        transformed = [process_value(x, constants) for x in val]
        return "[" + ", ".join(transformed) + "]"
    elif isinstance(val, str):
        # Возможно строка - вычислительное выражение
        # Формат: '@(...)'
        if val.startswith("@(") and val.endswith(")"):
            expr_body = val[2:-1].strip()
            tokens = expr_body.split()
            result = evaluate_postfix_expression(tokens, constants)
            return str(result)
        else:
            # Строковые литералы в синтаксисе не описаны, значит ошибка
            # Или можно считать, что строки не поддерживаются
            raise ConfigError(f"String '{val}' not supported as a value.")
    elif isinstance(val, (int, float)):
        # Число
        return str(val)
    else:
        raise ConfigError(f"Unsupported JSON value type: {type(val)}")


def main():
    parser = argparse.ArgumentParser(description="JSON to Config Language Converter")
    parser.add_argument("--input", required=True, help="Path to input JSON")
    parser.add_argument("--output", required=True, help="Path to output file")
    args = parser.parse_args()

    # Считываем JSON
    with open(args.input, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Ожидается ключ "constants" на верхнем уровне
    if "constants" not in data:
        raise ConfigError("No 'constants' section in JSON.")

    constants_section = data["constants"]
    # Проверяем имена констант
    # Имена: [a-z][a-z0-9_]* - можно проверить регексом
    import re
    name_pattern = re.compile(r'^[a-z][a-z0-9_]*$')

    constants = {}
    for k, v in constants_section.items():
        if not name_pattern.match(k):
            raise ConfigError(f"Invalid constant name '{k}'.")
        # v может быть числом или массивом
        if isinstance(v, (int, float)):
            constants[k] = v
        elif isinstance(v, list):
            # Проверим, что массив состоит только из чисел или вложенных структур?
            # По заданию значения массива - это числа или массивы.
            # Разрешим вложенные массивы целиком:
            def check_array(arr):
                for elem in arr:
                    if isinstance(elem, (int, float)):
                        continue
                    elif isinstance(elem, list):
                        check_array(elem)
                    else:
                        raise ConfigError("Array can contain only numbers or nested arrays.")

            check_array(v)
            constants[k] = v
        else:
            raise ConfigError(f"Constant '{k}' must be a number or an array.")

    # Убираем "constants" из данных
    del data["constants"]

    # Теперь осталось всё остальное преобразовать
    # Для каждого ключа на верхнем уровне генерируем:
    # const <name> = <value>;
    # где <value> - результат process_value

    output_lines = []
    # Сначала вывести все константы
    for cn, cv in constants.items():
        if isinstance(cv, list):
            # преобразовать массив в строку
            def arr_to_str(a):
                return "[" + ", ".join(arr_to_str(x) if isinstance(x, list) else str(x) for x in a) + "]"

            val_str = arr_to_str(cv)
        else:
            val_str = str(cv)
        output_lines.append(f"const {cn} = {val_str};")

    # Остальные ключи:
    for k, v in data.items():
        if not name_pattern.match(k):
            raise ConfigError(f"Invalid top-level name '{k}'.")
        val_str = process_value(v, constants)
        output_lines.append(f"const {k} = {val_str};")

    with open(args.output, "w", encoding="utf-8") as f:
        for line in output_lines:
            f.write(line + "\n")


if __name__ == "__main__":
    try:
        main()
    except ConfigError as e:
        print("Error:", e)
        sys.exit(1)
