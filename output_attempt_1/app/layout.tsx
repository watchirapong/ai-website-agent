// app/layout.tsx
import './globals.css';
import { Inter } from 'next/font/google';

const inter = Inter({ subsets: ['latin'] });

export const metadata = {
  title: 'The Daily Grind Coffee Co.',
  description: 'Artisan coffee and baked goods crafted with passion.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-gray-50 text-gray-800`}>
        {children}
      </body>
    </html>
  );
}