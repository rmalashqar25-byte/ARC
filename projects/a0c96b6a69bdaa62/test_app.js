const test = require('node:test');
const assert = require('node:assert/strict');
const { calculate } = require('./app.js');

test('addition with integers and decimals', () => {
  assert.equal(calculate(2, '+', 3), 5);
  assert.equal(calculate(0.1, '+', 0.2), 0.3);
  assert.equal(calculate('1.5', '+', '2.5'), 4);
});

test('subtraction with integers and decimals', () => {
  assert.equal(calculate(5, '-', 2), 3);
  assert.equal(calculate(1, '-', 0.9), 0.1);
});

test('multiplication', () => {
  assert.equal(calculate(4, '*', 2.5), 10);
  assert.equal(calculate(-3, '*', 3), -9);
});

test('division', () => {
  assert.equal(calculate(10, '/', 2), 5);
  assert.equal(calculate(7, '/', 2), 3.5);
});

test('divide by zero error handling', () => {
  assert.throws(() => calculate(5, '/', 0), {
    name: 'Error',
    message: 'Cannot divide by zero'
  });
});

test('invalid operator error handling', () => {
  assert.throws(() => calculate(2, '%', 3), {
    name: 'Error',
    message: 'Invalid operator'
  });
});

test('invalid number error handling', () => {
  assert.throws(() => calculate('abc', '+', 2), {
    name: 'Error',
    message: 'Invalid number input'
  });
});