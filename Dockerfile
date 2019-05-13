from knapenlab/nd:0.0.10gillesdev

RUN ["apt-get", "update"]
RUN ["apt-get", "install", "-y", "zsh"]

RUN wget -qO- "https://cmake.org/files/v3.12/cmake-3.12.2-Linux-x86_64.tar.gz" | tar --strip-components=1 -xz -C /usr/local

ENV ANTSPATH="/opt/ants-master/bin" \
    PATH="/opt/ants-master/bin:$PATH" \
    LD_LIBRARY_PATH="/opt/ants-master/lib:$LD_LIBRARY_PATH"

RUN mkdir -p /tmp/ants/build \
    && git clone https://github.com/ANTsX/ANTs.git /tmp/ants/source \
    && cd /tmp/ants/build \
    && cmake -DBUILD_SHARED_LIBS=ON} /tmp/ants/source \
    && make -j 5 \
    && mkdir -p /opt/ants-master/ \
    && mv bin lib /opt/ants-master/ \
    && mv /tmp/ants/source/Scripts/* /opt/ants-master/bin/ \
    && rm -rf /tmp/ants

RUN wget https://github.com/robbyrussell/oh-my-zsh/raw/master/tools/install.sh -O - | zsh || true

WORKDIR /src
RUN echo "source activate neuro\n. ${FSLDIR}/etc/fslconf/fsl.sh" >> ~/.zshrc
RUN bash -c "source activate neuro && pip install lxml --upgrade"

RUN apt-get update -qq && apt-get install -y python python-pip python-dev build-essential software-properties-common openjdk-8-jdk
RUN ln -svT "/usr/lib/jvm/java-8-openjdk-$(dpkg --print-architecture)" /docker-java-home
ENV JAVA_HOME /docker-java-home
ENV JCC_JDK /docker-java-home 
RUN apt-get install -y jcc

COPY nighres /nighres 

RUN cd /nighres \
    && bash -c "source activate neuro && pip install jcc" \
    && bash -c "./build_conda.sh neuro" \
    && bash -c "source activate neuro && python setup.py develop"
    
COPY ./analysis /src
COPY nipype.cfg /root/.nipype/nipype.cfg

RUN bash -c "source activate neuro && pip uninstall -y pandas && pip install pandas==0.23" \
    && bash -c "source activate neuro && pip uninstall -y templateflow && pip install templateflow"

COPY ./fmriprep /fmriprep
RUN bash -c "source activate neuro && pip uninstall -y fmriprep && cd /fmriprep && python setup.py develop"

COPY pymp2rage /pymp2rage
RUN bash -c "source activate neuro && pip uninstall -y pymp2rage && cd /pymp2rage && python setup.py develop"

COPY pybids /pybids
RUN bash -c "source activate neuro && pip uninstall -y pybids && cd /pybids && python setup.py develop"

COPY spynoza /spynoza
RUN bash -c "source activate neuro && pip uninstall -y spynoza && cd /pybids && python setup.py develop"

RUN bash -c "source activate neuro && pip install scikit-image --upgrade"
RUN bash -c "source activate neuro && pip install templateflow --upgrade"
