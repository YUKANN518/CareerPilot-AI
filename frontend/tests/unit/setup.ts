import { afterEach } from "vitest"

HTMLDialogElement.prototype.showModal = function showModal(): void {
  this.setAttribute("open", "")
}
HTMLDialogElement.prototype.close = function close(): void {
  this.removeAttribute("open")
}

afterEach(() => {
  localStorage.clear()
})
