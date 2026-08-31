export function rulesLayoutClass(category: string): string {
  return category === "price"
    ? "rules-page__layout--with-side"
    : "rules-page__layout--full"
}
