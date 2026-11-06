function calculate(a, op, b) {
  const numA = Number(a);
  const numB = Number(b);

  if (Number.isNaN(numA) || Number.isNaN(numB)) {
    throw new Error('Invalid number input');
  }

  let result;
  switch (op) {
    case '+':
      result = numA + numB;
      break;
    case '-':
      result = numA - numB;
      break;
    case '*':
      result = numA * numB;
      break;
    case '/':
      if (numB === 0) {
        throw new Error('Cannot divide by zero');
      }
      result = numA / numB;
      break;
    default:
      throw new Error('Invalid operator');
  }

  return Number(result.toFixed(10)) / 1;
}

if (typeof document !== 'undefined') {
  window.addEventListener('DOMContentLoaded', () => {
    const display = document.getElementById('display');
    let currentInput = '0';
    let previousInput = null;
    let operator = null;
    let shouldResetDisplay = false;

    function updateDisplay() {
      if (display) display.textContent = currentInput;
    }

    function handleNumber(numStr) {
      if (currentInput === '0' || shouldResetDisplay) {
        currentInput = numStr;
        shouldResetDisplay = false;
      } else {
        currentInput += numStr;
      }
      updateDisplay();
    }

    function handleDecimal() {
      if (shouldResetDisplay) {
        currentInput = '0.';
        shouldResetDisplay = false;
      } else if (!currentInput.includes('.')) {
        currentInput += '.';
      }
      updateDisplay();
    }

    function handleOperator(opStr) {
      if (operator && !shouldResetDisplay && previousInput !== null) {
        handleEquals();
      }
      previousInput = currentInput;
      operator = opStr;
      shouldResetDisplay = true;
    }

    function handleEquals() {
      if (operator === null || previousInput === null) return;
      try {
        const result = calculate(previousInput, operator, currentInput);
        currentInput = String(result);
        operator = null;
        previousInput = null;
        shouldResetDisplay = true;
      } catch (err) {
        currentInput = 'Error';
        operator = null;
        previousInput = null;
        shouldResetDisplay = true;
      }
      updateDisplay();
    }

    function handleClear() {
      currentInput = '0';
      previousInput = null;
      operator = null;
      shouldResetDisplay = false;
      updateDisplay();
    }

    document.querySelectorAll('.btn').forEach((button) => {
      button.addEventListener('click', () => {
        const action = button.dataset.action;
        const value = button.dataset.value;

        if (!action) {
          handleNumber(value);
        } else if (action === 'decimal') {
          handleDecimal();
        } else if (action === 'operator') {
          handleOperator(value);
        } else if (action === 'equals') {
          handleEquals();
        } else if (action === 'clear') {
          handleClear();
        }
      });
    });
  });
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { calculate };
}