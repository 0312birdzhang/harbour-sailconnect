// Independent scalar 2x2 reference for the AArch64 half-scale SIMD path.
#include "convert.h"
#include <vector>
#include <cstdio>
#include <cstdlib>
#include <cstring>

int main() {
    for (int scale : {2,3}) for (bool nv12 : {false, true}) for (bool flip : {false, true}) {
        const int sw=12*scale, sh=24*scale, dw=48, dh=24, stride=sw*4+16;
        std::vector<unsigned char> src(stride*sh), expected(dw*dh*3/2, 128);
        for (size_t i=0; i<src.size(); ++i) src[i]=(i*73+i/11)%256;
        memset(expected.data(),16,dw*dh);
        // Half-size portrait content is 12x24 at x=18, including a 4px SIMD tail.
        for (int y=0;y<24;++y) for (int x=0;x<12;++x) {
            int c[3]={};
            for (int j=0;j<scale;++j) for (int i=0;i<scale;++i) {
                int sy=y*scale+j;
                if (flip) sy=sh-1-sy;
                for (int k=0;k<3;++k) c[k]+=src[sy*stride+(x*scale+i)*4+k];
            }
            const int r=c[0]/(scale*scale),g=c[1]/(scale*scale),b=c[2]/(scale*scale);
            expected[y*dw+18+x]=((66*r+129*g+25*b+128)>>8)+16;
            if (!(x%2) && !(y%2)) {
                const int u=((-38*r-74*g+112*b+128)>>8)+128;
                const int v=((112*r-94*g-18*b+128)>>8)+128;
                const int n=(y/2)*(dw/2)+(18+x)/2;
                if(nv12) {expected[dw*dh+n*2]=u;expected[dw*dh+n*2+1]=v;}
                else {expected[dw*dh+n]=u;expected[dw*dh+dw*dh/4+n]=v;}
            }
        }
        imira::FrameConverter converter;
        converter.configure(dw,dh,nv12);
        size_t size=0;
        auto actual=converter.convert(src.data(),sw,sh,stride,flip,0,&size);
        if (!actual || size!=expected.size() || memcmp(actual,expected.data(),size)) {
            fprintf(stderr,"SIMD mismatch nv12=%d flip=%d\n",nv12,flip);free(actual);return 1;
        }
        free(actual);
    }
    puts("2x/3x SIMD: scalar parity passed for I420/NV12, both row orders and tails");
}
