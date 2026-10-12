"use client";
export default function ErrorPage({ reset }: { reset: () => void }) { return <section className="narrow"><h1>Something went wrong</h1><p>The store couldn't complete this request. Please try again in a moment.</p><button onClick={reset}>Try again</button></section>; }
