'use client';

import { Hero } from '@/components/hero';
import { useRouter } from 'next/navigation';
// import UseCases from '@/components/use-cases';

export default function Home() {
  const router = useRouter();

  const handleUploadClick = () => {
    router.push('/upload');
  };

  return (
    <div className="min-h-screen w-full bg-black flex flex-col overflow-x-hidden">
      <div className="h-screen w-full relative">
        <div className="h-full z-10 relative">
          <Hero onUploadClick={handleUploadClick} />
        </div>
      </div>

      {/* <div className="w-full">
        <UseCases />
      </div> */}

      {/* Footer */}
    </div>
  );
}
