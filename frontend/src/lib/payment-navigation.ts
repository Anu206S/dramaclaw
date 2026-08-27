// SPDX-License-Identifier: Elastic-2.0
// Copyright (c) 2026 ClaymoreLab

export const CHECKOUT_DRAFT_KEY = "dramaclaw-checkout-draft";
export const CHECKOUT_RETURN_KEY = "dramaclaw-checkout-return";
export const PAYMENT_RETURN_ORDER_KEY = "dramaclaw-payment-return-order";
export const PAYMENT_RETURN_ORDER_ID_KEY = "dramaclaw-payment-return-order-id";
export const OPEN_CREDIT_CENTER_KEY = "dramaclaw-open-credit-center";
export const CREDIT_CENTER_TAB_KEY = "dramaclaw-credit-center-tab";

export function safePaymentReturnPath(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return "/";
  if (value === "/checkout" || value.startsWith("/payment-return")) return "/";
  return value;
}

export function paymentOrderNumberFromSearch(search: string): string | null {
  const parameters = new URLSearchParams(search);
  for (const key of ["mchOrderNo", "out_trade_no", "merchant_order_no"]) {
    const value = parameters.get(key)?.trim();
    if (value) return value;
  }
  return null;
}
