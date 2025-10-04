from core.utils import is_similar

class CalculatorCommand:
    def execute(self, message):
        try:
            parts = message.split()
            if not is_similar(parts[0].lower(), "oblicz", threshold=0.7):
                return None

            num1 = float(parts[1])
            operation = parts[2]
            num2 = float(parts[3])

            if operation == "+":
                return str(num1 + num2)
            elif operation == "-":
                return str(num1 - num2)
            elif operation == "*":
                return str(num1 * num2)
            elif operation == "/":
                return str(num1 / num2)
            else:
                return "Invalid operation."
        except Exception as e:
            return f"Error: {e}"
