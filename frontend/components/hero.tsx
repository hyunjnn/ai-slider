import { ChevronDown, ChevronRight } from 'lucide-react';
import { motion } from 'framer-motion';
import CustomLogo from './custom-logo';

interface HeroProps {
  onUploadClick: () => void;
}
export const Hero = ({ onUploadClick }: HeroProps) => {
  const scrollToNextSection = () => {
    window.scrollTo({
      top: window.innerHeight,
      behavior: 'smooth',
    });
  };

  return (
    <div className="h-screen w-full flex items-center justify-center">
      <div className="relative z-10 container mx-auto px-4 md:px-6">
        {/* App Logo */}
        <div className="max-w-4xl mx-auto text-center">
          <h1 className="text-3xl sm:text-5xl md:text-7xl lg:text-8xl font-bold tracking-tight">
            <CustomLogo size="xl" withLink={false} className="inline-block text-zinc-300" text="AI Slides" />
          </h1>
        </div>

        {/* Move To Upload Page */}
        <button
          onClick={onUploadClick}
          className="px-6 py-3 mt-10 bg-gray-300 hover:bg-gray-200 text-gray-900 rounded-full text-base md:text-lg font-medium flex items-center gap-2 mx-auto transition-colors cursor-pointer"
        >
          Quick Start <ChevronRight className="w-4 h-4" />
        </button>
      </div>

      {/* Scroll To Next Section */}
      <motion.div
        className="absolute bottom-8 left-0 right-0 mx-auto w-10 flex justify-center cursor-pointer"
        onClick={scrollToNextSection}
        initial={{ opacity: 0 }}
        animate={{
          opacity: 1,
          y: [0, 10, 0],
        }}
        transition={{
          delay: 2,
          y: {
            repeat: Infinity,
            duration: 2,
            ease: 'easeInOut',
          },
        }}
        whileHover={{ scale: 1.1 }}
      >
        <div className="w-10 h-10 rounded-full bg-zinc-100 shadow-md flex items-center justify-center">
          <ChevronDown className="w-6 h-6 text-black" />
        </div>
      </motion.div>
    </div>
  );
};
