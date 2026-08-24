import { redirect } from 'next/navigation'

// /orders has no dedicated page: open orders render inside /positions
// (Orders panel). Keep the URL alive for bookmarks/deep links.
export default function OrdersPage() {
  redirect('/positions')
}
